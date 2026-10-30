from typing import Protocol


class Runner(Protocol):
    def run(self, prompt: str) -> str: ...


def generate(prompt: str, runner: Runner) -> str:
    if not prompt.strip() or len(prompt) > 4000:
        raise ValueError("prompt must contain 1..4000 characters and non-whitespace")
    answer = runner.run(prompt)
    if not answer.strip() or len(answer) > 8000:
        raise ValueError("provider returned an invalid answer")
    return answer
