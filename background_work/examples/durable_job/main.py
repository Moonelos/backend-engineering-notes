import argparse
import os
import time
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

import store

app = FastAPI()


class Document(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)


@app.post("/document-parses")
def submit(body: Document, idempotency_key: str = Header(min_length=1, max_length=200)):
    try:
        job = store.submit(idempotency_key, body.text)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return JSONResponse(jsonable_encoder(job), status_code=202,
                        headers={"Location": f"/document-parses/{job['id']}"})


@app.get("/document-parses/{job_id}")
def status(job_id: UUID):
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init","worker","once","claim-and-exit"])
    args = parser.parse_args()
    if args.action == "init":
        store.initialize()
        print("schema ready")
    elif args.action == "claim-and-exit":
        job = store.claim(lease_seconds=2)
        print("claimed", job["id"], "then process exits without completion", flush=True)
        os._exit(17)  # Deliberate crash for the recovery exercise.
    elif args.action == "once":
        print("completed", store.execute())
    else:
        while True:
            result = store.execute()
            if result:
                print("completed", result, flush=True)
            time.sleep(0.2)
