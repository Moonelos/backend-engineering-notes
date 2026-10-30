from fastapi.testclient import TestClient
from safe_call_app import create_app


def test_dependency_outage_preserves_local_routes_and_health():
    with TestClient(create_app(provider_mode='outage')) as client:
        assert client.get('/orders/ord_42').status_code == 502
        assert client.get('/ready').status_code == 200
        assert client.get('/live').status_code == 200
        assert client.get('/local').json() == {'local':'ok'}


def test_draining_changes_readiness_without_restart():
    app = create_app()
    with TestClient(app) as client:
        assert client.get('/orders/ord_42').status_code == 200
        app.state.accepting = False
        assert client.get('/ready').status_code == 503
        assert client.get('/orders/ord_42').json()['code'] == 'DRAINING'
        assert client.get('/live').status_code == 200
