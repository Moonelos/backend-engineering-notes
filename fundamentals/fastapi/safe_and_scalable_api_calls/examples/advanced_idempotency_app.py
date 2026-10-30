"""Local SQL payment ledger only; no card network or billable provider."""
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from advanced_idempotency import claim, complete_local, Conflict, Busy, StaleOwner

app=FastAPI()

class Payment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    amount: int=Field(gt=0,le=1_000_000,strict=True)

@app.post('/payments')
def payment(payload: Payment, idempotency_key: str=Header(alias='Idempotency-Key',min_length=1,max_length=200),
            authorization: str=Header(default='')):
    # FastAPI executes this synchronous DB endpoint in its threadpool.
    if authorization!='Bearer local-demo':
        raise HTTPException(401,'Authentication required')
    try:
        owner=claim('verified-demo-tenant','POST /payments',idempotency_key,payload.model_dump())
        status,body=complete_local(owner,payload.amount)
    except Conflict:
        raise HTTPException(422,'Idempotency key has different request meaning')
    except (Busy,StaleOwner):
        raise HTTPException(409,'Operation pending; retry with the same key',headers={'Retry-After':'1'})
    return JSONResponse(body,status_code=status)
