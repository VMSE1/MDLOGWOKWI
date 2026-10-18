"""HTTP API сервера MADILOG. Запуск: uvicorn server.app:app --port 8000"""
import os
from typing import List, Optional

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .engine import Engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = Engine(os.environ.get("MADILOG_DB", os.path.join(ROOT, "registry.db")))
app = FastAPI(title="MADILOG: идентификация морских дронов (демо)")


class Pose(BaseModel):
    lat: float
    lon: float
    heading_deg: float = 0.0


class Detection(BaseModel):
    kind: str                       # "echo" | "transponder"
    range_m: float
    az_deg: Optional[float] = None  # None, если у модуля нет угловой решётки
    snr_db: Optional[float] = None
    id: Optional[str] = None
    crc_ok: bool = True
    counter: Optional[int] = None
    mac: Optional[str] = None
    depth_m: Optional[float] = None


class Payload(BaseModel):
    module_id: str
    ts: Optional[str] = None
    pose: Pose
    sound_speed_mps: float = 1500.0
    detections: List[Detection]


class DroneIn(BaseModel):
    id: str
    owner: str
    mission: str
    allowed: bool = True
    key: Optional[str] = None


@app.post("/api/v1/detections")
async def detections(p: Payload):
    ENGINE.ingest(p.model_dump())
    return {"ok": True, "accepted": len(p.detections)}


@app.get("/api/v1/state")
async def state():
    return ENGINE.snapshot()


@app.get("/api/v1/registry")
async def registry():
    return ENGINE.reg.all()


@app.post("/api/v1/registry")
async def registry_upsert(d: DroneIn):
    ENGINE.reg.upsert(d.id, d.owner, d.mission, d.allowed, d.key)
    return {"ok": True}


@app.post("/api/v1/reset")
async def reset():
    ENGINE.reset()
    return {"ok": True}


app.mount("/ui", StaticFiles(directory=os.path.join(ROOT, "ui"), html=True), name="ui")


@app.get("/")
async def index():
    return RedirectResponse("/ui/")
