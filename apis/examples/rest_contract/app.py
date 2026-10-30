"""In-process authorization-policy fixture; production authentication is deliberately injected."""
from dataclasses import dataclass
from uuid import uuid4
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

@dataclass(frozen=True)
class Principal:
    tenant_id: int

class OrderOut(BaseModel):
    id: str
    status: str

app = FastAPI()
ORDERS = {'ord_A': {'id': 'ord_A', 'tenant_id': 7, 'status': 'paid'},
          'ord_B': {'id': 'ord_B', 'tenant_id': 8, 'status': 'pending'}}

def authenticate() -> Principal:
    # Install your verified issuer/session dependency in the real application.
    # This fixture fails closed unless the test explicitly overrides it.
    raise HTTPException(401, 'Authentication required', headers={'WWW-Authenticate': 'Bearer'})

@app.get('/orders/{order_id}', response_model=OrderOut, operation_id='getOrder')
def get_order(order_id: str, request: Request, principal: Principal = Depends(authenticate)):
    row = ORDERS.get(order_id)
    if row is None or row['tenant_id'] != principal.tenant_id:
        return JSONResponse(status_code=404, media_type='application/problem+json', content={
            'type': 'https://api.example.com/problems/order-not-found',
            'title': 'Order not found', 'status': 404,
            'detail': 'No visible order has that identifier.', 'instance': request.url.path,
            'code': 'ORDER_NOT_FOUND', 'request_id': str(uuid4())})
    return row
