"""Narrow executable checks for the repaired fixture and transport contracts."""
import ast
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL

NOTES = Path(__file__).resolve().parents[1]


def function_from_note(note, name, namespace):
    blocks = re.findall(r"```python\n(.*?)\n```", (NOTES / note).read_text(), re.S)
    for block in blocks:
        try:
            parsed = ast.parse(block)
        except SyntaxError:
            continue
        for node in parsed.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                node.decorator_list = []
                module = ast.Module(body=[node], type_ignores=[])
                exec(compile(module, note, "exec"), namespace)
                return namespace[name]
    raise AssertionError(name)


def test_nested_override_restore_after_exception():
    db, auth = object(), object()
    baseline = object()
    app = SimpleNamespace(dependency_overrides={db: baseline})
    reset = function_from_note("07_fixtures.md", "reset_dependency_overrides", {"app": app})
    fixture = reset()
    next(fixture)
    app.dependency_overrides[auth] = lambda: "fake"
    try:
        fixture.throw(RuntimeError("test failed"))
    except RuntimeError:
        pass
    assert app.dependency_overrides == {db: baseline}


def test_override_uses_callable_identity():
    app = FastAPI()
    def user():
        return "real"
    def same_name_other_callable():
        return "unrelated"
    same_name_other_callable.__name__ = user.__name__
    @app.get("/")
    def route(value=Depends(user)):
        return {"user": value}
    app.dependency_overrides[same_name_other_callable] = lambda: "wrong-key"
    with TestClient(app) as client:
        assert client.get("/").json() == {"user": "real"}
        app.dependency_overrides[user] = lambda: "test"
        assert client.get("/").json() == {"user": "test"}


def test_sqlalchemy_url_needs_explicit_password_rendering():
    url = URL.create("postgresql", username="fixture", password="not-a-real-secret%", host="localhost", database="test")
    assert "***" in str(url)
    from configparser import ConfigParser
    config = ConfigParser()
    config["alembic"] = {"sqlalchemy.url": url.render_as_string(hide_password=False).replace("%", "%%")}
    assert config["alembic"]["sqlalchemy.url"] == url.render_as_string(hide_password=False)


def test_subtests_runtime_discovery(subtests):
    for item_id in [1, 2, 3]:
        with subtests.test(item_id=item_id):
            assert item_id > 0
