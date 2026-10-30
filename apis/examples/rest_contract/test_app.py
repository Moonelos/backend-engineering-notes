import pytest
from fastapi.testclient import TestClient
from .app import app, authenticate, Principal

@pytest.fixture
def client():
    app.dependency_overrides[authenticate] = lambda: Principal(tenant_id=7)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()

@pytest.mark.parametrize('order_id', ['ord_B', 'ord_missing'])
def test_invisible_order_uses_same_problem_contract(client, order_id):
    response = client.get(f'/orders/{order_id}')
    assert response.status_code == 404
    assert response.headers['content-type'].startswith('application/problem+json')
    assert response.json()['code'] == 'ORDER_NOT_FOUND'
    assert response.json()['detail'] == 'No visible order has that identifier.'

def test_allowed_order_filters_internal_fields(client):
    assert client.get('/orders/ord_A').json() == {'id': 'ord_A', 'status': 'paid'}

def test_openapi_operation_ids_are_unique(client):
    operations = [op['operationId'] for item in client.get('/openapi.json').json()['paths'].values()
                  for method, op in item.items() if method in {'get','post','put','patch','delete'}]
    assert len(operations) == len(set(operations))

def test_fixture_fails_closed_without_auth_override():
    with TestClient(app) as client:
        response = client.get('/orders/ord_A')
        assert response.status_code == 401
        assert response.headers['www-authenticate'] == 'Bearer'
