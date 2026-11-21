"""主链路冒烟：登录、占位、确认、对账。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app  # noqa: E402
from db import DB_PATH, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setattr("db.DB_PATH", db)
    # app.db 模块级已导入
    import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", db)
    if db.exists():
        db.unlink()
    init_db()
    yield


def _login(c: TestClient, user="admin", password="123456"):
    r = c.post("/api/login", json={"username": user, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_and_seed():
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json()["product"] == "档期预订"
        assert r.json()["slots"] >= 1


def test_hold_confirm_reconcile():
    with TestClient(app) as c:
        h = _login(c)
        r = c.post(
            "/api/holds",
            headers=h,
            json={"slot_code": "S-AM-01", "party_key": "P-T1", "seats": 1},
        )
        assert r.status_code == 200, r.text
        assert r.json()["disposition"] == "占位"
        hid = r.json()["hold_id"]
        r2 = c.post("/api/bookings/confirm", headers=h, json={"hold_id": hid})
        assert r2.status_code == 200, r2.text
        recon = c.get("/api/reconcile", headers=h).json()
        assert recon["all_ok"] is True


def test_overflow_to_waitlist():
    with TestClient(app) as c:
        h = _login(c)
        # S-EVE-03 capacity 6; fill
        for i in range(6):
            c.post(
                "/api/holds",
                headers=h,
                json={"slot_code": "S-EVE-03", "party_key": f"P-F{i}", "seats": 1},
            )
            holds = c.get("/api/holds", headers=h).json()["items"]
            hid = [x for x in holds if x["party_key"] == f"P-F{i}"][0]["id"]
            c.post("/api/bookings/confirm", headers=h, json={"hold_id": hid})
        r = c.post(
            "/api/holds",
            headers=h,
            json={"slot_code": "S-EVE-03", "party_key": "P-OVER", "seats": 1},
        )
        assert r.status_code == 200
        assert r.json()["disposition"] == "候补"


def test_viewer_forbidden_write():
    with TestClient(app) as c:
        h = _login(c, "viewer", "123456")
        r = c.post(
            "/api/holds",
            headers=h,
            json={"slot_code": "S-AM-01", "party_key": "X", "seats": 1},
        )
        assert r.status_code == 403
