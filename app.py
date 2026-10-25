from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Literal

app = FastAPI(title="TimeFault AI")

VALID_STATES = {"created", "ready", "running", "succeeded", "failed", "deleted"}


class RunCreate(BaseModel):
    run_id: str = Field(..., min_length=1)
    sandbox_name: str = Field(..., min_length=1)
    problem_id: str = Field(..., min_length=1)
    state: Literal["created", "ready", "running", "succeeded", "failed", "deleted"]
    execution_target: str = Field(..., min_length=1)

    @field_validator("sandbox_name")
    @classmethod
    def validate_sandbox(cls, value: str) -> str:
        if not value.startswith("sbx-"):
            raise ValueError("sandbox_name must start with 'sbx-'")
        return value

    @field_validator("execution_target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        if value != "celesto_sandbox":
            raise ValueError("execution_target must be 'celesto_sandbox'")
        return value


RUNS = [
    {
        "run_id": "demo-001",
        "sandbox_name": "sbx-seeddemo1",
        "problem_id": "CF-01",
        "state": "ready",
        "execution_target": "celesto_sandbox",
    }
]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/runs")
def list_runs() -> list[dict]:
    return RUNS


@app.post("/api/runs", status_code=201)
def create_run(payload: RunCreate) -> dict:
    if payload.state not in VALID_STATES:
        raise HTTPException(status_code=400, detail="invalid state")
    if not payload.sandbox_name.startswith("sbx-"):
        raise HTTPException(status_code=400, detail="invalid sandbox name")
    if payload.execution_target != "celesto_sandbox":
        raise HTTPException(status_code=400, detail="invalid execution target")
    RUNS.append(payload.model_dump())
    return payload.model_dump()
