from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

from modular_app.agents.api import Runner, generate
from modular_app.conversations.api import Answer, Conversations
from modular_app.usage.api import Usage


class RequestConflict(Exception):
    pass


@dataclass(frozen=True)
class WriteModules:
    conversations: Conversations
    usage: Usage


Transaction = Callable[[], AbstractContextManager[WriteModules]]


def answer_message(
    *, tenant: str, conversation_id: str, request_id: str, prompt: str,
    runner: Runner, transaction: Transaction,
) -> Answer:
    """Tenant is supplied by a trusted caller, never inferred from prompt content."""
    if not all(isinstance(value, str) and value.strip() and len(value) <= 100
               for value in (tenant, conversation_id, request_id)):
        raise ValueError("nonempty identifiers of at most 100 characters required")

    def existing(modules: WriteModules) -> Answer | None:
        modules.conversations.require(tenant, conversation_id)
        previous = modules.conversations.find_answer(tenant, request_id)
        if previous and (previous.conversation_id != conversation_id or previous.prompt != prompt):
            raise RequestConflict("request ID was already used for different input")
        return previous

    # Check access and replay before an expensive call. Release the DB lock first.
    with transaction() as modules:
        previous = existing(modules)
        if previous:
            return previous

    text = generate(prompt, runner)

    with transaction() as modules:
        # Recheck: another invocation may have completed during generation.
        previous = existing(modules)
        if previous:
            return previous
        answer = Answer(tenant, request_id, conversation_id, prompt, text)
        modules.conversations.append(answer)
        modules.usage.record_answer(tenant, request_id)
    return answer
