"""Small static guard for this example's absolute-import convention.

Not a general import graph analyzer: dynamic imports, aliases through re-exports,
runtime attribute access and SQL ownership require separate controls/review.
"""
import ast
from pathlib import Path

MODULES = {"agents", "conversations", "usage"}
EDGES = {"bootstrap", "demo"}


def violations(source: str, owner: str) -> list[str]:
    errors = []
    for node in ast.walk(ast.parse(source)):
        targets = []
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                errors.append("use absolute imports so the local guard can inspect them")
                continue
            base = node.module or ""
            targets = [base]
            if base == "modular_app" or base in {f"modular_app.{m}" for m in MODULES}:
                targets += [f"{base}.{alias.name}" for alias in node.names]
        for target in targets:
            parts = target.split(".")
            if len(parts) < 2 or parts[0] != "modular_app":
                continue
            destination = parts[1]
            if owner in MODULES and destination != owner:
                errors.append(f"{owner} cannot import {target}; coordinate in workflows")
            elif owner == "workflows" and destination in EDGES:
                errors.append(f"workflows cannot import composition edge {target}")
            elif (owner not in EDGES and owner != destination and destination in MODULES
                  and (len(parts) < 3 or parts[2] != "api")):
                errors.append(f"import {destination}.api instead of {target}")
    return errors


def check_tree(root: Path) -> list[str]:
    errors = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        owner = relative.parts[0].removesuffix(".py")
        errors.extend(f"{relative}: {error}" for error in violations(path.read_text(), owner))
    return errors


if __name__ == "__main__":
    failures = check_tree(Path(__file__).parent / "modular_app")
    if failures:
        raise SystemExit("\n".join(failures))
    print("module import boundaries: PASS")
