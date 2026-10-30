"""Exercises the same settings schema, mounted inputs and real ASGI lifecycle."""
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from fastapi.testclient import TestClient
from pydantic import ValidationError
from functools import lru_cache
from settings_lab import Settings, create_app

with tempfile.TemporaryDirectory(prefix='notes-settings-') as directory:
    root = Path(directory);secrets = root/'secrets';secrets.mkdir()
    (secrets/'database').write_text(json.dumps({'url':'sqlite:///fixture.db'}))
    def rotate(version):
        (secrets/'auth').write_text(json.dumps({'secret_key':'fake-only-'+version,'version':version}))
    rotate('v7')
    (secrets/'debug').write_text('true')
    dotenv=root/'.env';dotenv.write_text('DEBUG=false\nENVIRONMENT=test\n')
    @lru_cache
    def load():return Settings(_env_file=dotenv,_secrets_dir=secrets)
    with patch.dict(os.environ, {},clear=True):
        assert Settings(_env_file=dotenv,_secrets_dir=secrets).debug is False
    with patch.dict(os.environ, {'DEBUG':'true'},clear=True):
        assert load().debug is True
        assert Settings(debug=False,_env_file=dotenv,_secrets_dir=secrets).debug is False
        app=create_app(load)
        with TestClient(app) as client:
            assert client.get('/health').json()['credential_version']=='v7'
            rotate('v8')
            assert load().auth.version=='v7'
            assert client.get('/health').json()['credential_version']=='v7'
        assert app.state.client.closed
        load.cache_clear()
        replacement=create_app(load)
        with TestClient(replacement) as client:
            assert client.get('/health').json()['credential_version']=='v8'
        # Higher-precedence environment can still mask a rotated file.
        with patch.dict(os.environ, {'AUTH__VERSION':'env-v9'}):
            assert Settings(_env_file=dotenv,_secrets_dir=secrets).auth.version=='env-v9'
        with patch.dict(os.environ, {'DATABASE__POOL_SIZE':'0'}):
            load.cache_clear()
            try:
                with TestClient(create_app(load)):
                    raise AssertionError('invalid startup must not serve')
            except ValidationError as error:
                assert 'fake-only' not in str(error)
                print('invalid configuration rejected before serving; no credential in diagnostic')
    print('PASS: init > environment > dotenv > files; cached v7; closed client; restarted v8; env masks file')
