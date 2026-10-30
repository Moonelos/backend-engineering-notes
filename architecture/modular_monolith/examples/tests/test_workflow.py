import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

from check_boundaries import check_tree, violations
from modular_app.agents._fake import EchoRunner
from modular_app.bootstrap import Database
from modular_app.conversations.api import MissingConversation
from modular_app.workflows.answer import RequestConflict, WriteModules, answer_message


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Database(Path(self.directory.name) / "test.sqlite")
        self.database.initialize()
        with self.database.transaction() as modules:
            modules.conversations.create("acme", "C-1")
        self.arguments = dict(tenant="acme", conversation_id="C-1", request_id="R-1",
                              prompt="hello", runner=EchoRunner(), transaction=self.database.transaction)

    def test_replay_does_not_generate_or_count_again(self):
        first = answer_message(**self.arguments)

        class MustNotRun:
            def run(self, prompt):
                raise AssertionError("replay called provider")

        replay = answer_message(**(self.arguments | {"runner": MustNotRun()}))
        self.assertEqual(first, replay)
        with self.database.transaction() as modules:
            self.assertEqual(modules.usage.total("acme"), 1)

    def test_reused_key_with_changed_prompt_is_conflict(self):
        answer_message(**self.arguments)
        with self.assertRaises(RequestConflict):
            answer_message(**(self.arguments | {"prompt": "different"}))

    def test_old_writer_survives_additive_nullable_column(self):
        # A migration runner changes the module-owned schema; old code still runs.
        connection = self.database.connect()
        try:
            connection.execute("ALTER TABLE answers ADD COLUMN model_version TEXT")
        finally:
            connection.close()
        answer = answer_message(**self.arguments)
        self.assertEqual(answer.text, "Answer: hello")
        with self.database.transaction() as modules:
            self.assertEqual(modules.conversations.find_answer("acme", "R-1"), answer)
            self.assertEqual(modules.usage.total("acme"), 1)

    def test_wrong_tenant_cannot_read_conversation(self):
        with self.assertRaises(MissingConversation):
            answer_message(**(self.arguments | {"tenant": "other"}))

    def test_provider_failure_leaves_no_local_effect(self):
        class Fails:
            def run(self, prompt):
                raise TimeoutError("provider deadline")

        with self.assertRaises(TimeoutError):
            answer_message(**(self.arguments | {"runner": Fails()}))
        with self.database.transaction() as modules:
            self.assertIsNone(modules.conversations.find_answer("acme", "R-1"))
            self.assertEqual(modules.usage.total("acme"), 0)

    def test_second_write_failure_rolls_back_first_and_retry_succeeds(self):
        class RejectUsage:
            def record_answer(self, tenant, request_id):
                raise sqlite3.OperationalError("injected write failure")

        @contextmanager
        def failing_transaction():
            with self.database.transaction() as modules:
                yield WriteModules(modules.conversations, RejectUsage())

        with self.assertRaises(sqlite3.OperationalError):
            answer_message(**(self.arguments | {"transaction": failing_transaction}))
        with self.database.transaction() as modules:
            self.assertIsNone(modules.conversations.find_answer("acme", "R-1"))
            self.assertEqual(modules.usage.total("acme"), 0)
        answer_message(**self.arguments)
        with self.database.transaction() as modules:
            self.assertEqual(modules.usage.total("acme"), 1)

    def test_concurrent_duplicates_generate_twice_but_commit_once(self):
        barrier = Barrier(2)

        class ConcurrentRunner:
            def run(self, prompt):
                barrier.wait(timeout=5)
                return "same answer"

        arguments = self.arguments | {"runner": ConcurrentRunner()}
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: answer_message(**arguments), range(2)))
        self.assertEqual(results[0], results[1])
        with self.database.transaction() as modules:
            self.assertEqual(modules.usage.total("acme"), 1)


class BoundaryTests(unittest.TestCase):
    def test_actual_tree(self):
        root = Path(__file__).resolve().parents[1] / "modular_app"
        self.assertEqual(check_tree(root), [])

    def test_invalid_imports_are_rejected(self):
        cases = [
            ("from modular_app.usage.api import Usage", "conversations"),
            ("from modular_app.conversations._schema import SCHEMA", "workflows"),
            ("from modular_app import bootstrap", "workflows"),
            ("from .api import Usage", "usage"),
        ]
        for source, owner in cases:
            with self.subTest(source=source):
                self.assertTrue(violations(source, owner))


if __name__ == "__main__":
    unittest.main()
