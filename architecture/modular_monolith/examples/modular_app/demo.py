from pathlib import Path
from tempfile import TemporaryDirectory

from modular_app.agents._fake import EchoRunner
from modular_app.bootstrap import Database
from modular_app.workflows.answer import answer_message


def main() -> None:
    with TemporaryDirectory() as directory:
        database = Database(Path(directory) / "demo.sqlite")
        database.initialize()
        with database.transaction() as modules:
            modules.conversations.create("acme", "C-1")
        arguments = dict(tenant="acme", conversation_id="C-1", request_id="R-1",
                         prompt="hello", runner=EchoRunner(), transaction=database.transaction)
        first = answer_message(**arguments)
        replay = answer_message(**arguments)
        print(f"R-1: {first.text}")
        print(f"replay equals original: {replay == first}")
        with database.transaction() as modules:
            print(f"accepted answers: {modules.usage.total('acme')}")


if __name__ == "__main__":
    main()
