"""空桩可点：release / transfer 登记任务但不改正式册。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app  # noqa: E402
from db import init_db  # noqa: E402
import db as dbmod  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    if db.exists():
        db.unlink()
    init_db()
    yield


def _login(c):
    r = c.post("/api/login", json={"username": "admin", "password": "123456"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_release_stub():
    with TestClient(app) as c:
        h = _login(c)
        books = c.get("/api/bookings", headers=h).json()["items"]
        assert books
        r = c.post("/api/release", headers=h, json={"booking_id": books[0]["id"]})
        assert r.status_code == 200
        assert r.json()["stub"] is True
        # 正式册未变
        books2 = c.get("/api/bookings", headers=h).json()["items"]
        assert books2[0]["status"] == "已确认"


def test_transfer_stub():
    with TestClient(app) as c:
        h = _login(c)
        books = c.get("/api/bookings", headers=h).json()["items"]
        r = c.post(
            "/api/transfer",
            headers=h,
            json={"booking_id": books[0]["id"], "to_slot_code": "S-PM-02"},
        )
        assert r.status_code == 200
        assert r.json()["stub"] is True
