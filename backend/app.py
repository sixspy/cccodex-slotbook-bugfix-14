"""档期预订 — FastAPI 入口。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from audit_svc import router as audit_router
from auth import router as auth_router
from confirm_svc import router as confirm_router
from db import FRONTEND, PRODUCT_META, init_db
from hold_svc import router as hold_router
from locks import router as locks_router
from reconcile_svc import router as reconcile_router
from release_svc import router as release_router
from slots_svc import router as slots_router
from transfer_svc import router as transfer_router
from waitlist_svc import router as waitlist_router

PRODUCT = "档期预订"
SKELETON = "档期先占位后确认才进正式册，冲突进候补，确认快照与档期对账"

app = FastAPI(title=PRODUCT, description=SKELETON)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    auth_router,
    slots_router,
    hold_router,
    confirm_router,
    waitlist_router,
    reconcile_router,
    locks_router,
    audit_router,
    release_router,
    transfer_router,
):
    app.include_router(r)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/health")
def health():
    from db import DB_PATH, connect

    with connect() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM slots").fetchone()["c"]
        tables = conn.execute(
            "SELECT COUNT(*) c FROM sqlite_master WHERE type='table'"
        ).fetchone()["c"]
    return {
        "ok": True,
        "product": PRODUCT,
        "skeleton": SKELETON,
        "slots": n,
        "tables": tables,
        "db": str(DB_PATH),
        "meta": PRODUCT_META,
    }


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
