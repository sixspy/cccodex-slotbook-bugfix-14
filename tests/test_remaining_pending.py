"""BUGFIX-14 余席漏扣待确认：先红后绿。

夹具 fixtures/remaining_false_green.json 描述一个「有待确认却余席虚高」的档期：
容量 8、已订 0、待确认 2，旧口径余席显示 8（虚高），正确值 6。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app  # noqa: E402
from db import init_db  # noqa: E402
import db as dbmod  # noqa: E402

FALSE_GREEN = json.loads(
    (ROOT / "fixtures" / "remaining_false_green.json").read_text(encoding="utf-8")
)


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    if db.exists():
        db.unlink()
    init_db()
    yield


def _login(c: TestClient, user: str = "admin", password: str = "123456"):
    r = c.post("/api/login", json={"username": user, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _five_surfaces(c: TestClient, h: dict) -> dict:
    """余席页 / 待确认行 / 候补页 / 对账页 / 审计页 五处同态读数。"""
    code = FALSE_GREEN["slot_code"]
    slots = {i["code"]: i for i in c.get("/api/slots", headers=h).json()["items"]}
    holds = [
        i for i in c.get("/api/holds", headers=h).json()["items"]
        if i["slot_code"] == code
    ]
    waits = [
        i for i in c.get("/api/waitlist", headers=h).json()["items"]
        if i["slot_code"] == code
    ]
    recon = {
        i["slot_code"]: i
        for i in c.get("/api/reconcile", headers=h).json()["items"]
    }
    audit = c.get("/api/audit", headers=h).json()
    audit_rem = {
        i["slot_code"]: i for i in audit.get("remaining", [])
    }
    return {
        "slots": slots[code],
        "hold": holds[0],
        "wait": waits[0],
        "reconcile": recon[code],
        "audit": audit_rem.get(code),
    }


def test_false_green_pending_must_reduce_remaining_everywhere():
    """假绿夹具：待确认 2 席未扣，余席必须 6，且五处同态。"""
    with TestClient(app) as c:
        h = _login(c)
        code = FALSE_GREEN["slot_code"]

        detail = c.get(f"/api/slots/{code}", headers=h)
        assert detail.status_code == 200, detail.text
        d = detail.json()
        # 夹具前置：旧口径余席虚高（capacity-booked=8）而实际待确认 2 席
        assert d["capacity"] == FALSE_GREEN["capacity"]
        assert d["booked"] == FALSE_GREEN["booked"]
        pending = sum(
            i["seats"]
            for i in c.get("/api/holds", headers=h).json()["items"]
            if i["slot_code"] == code and i["status"] == "占位中"
        )
        assert pending == FALSE_GREEN["pending_seats"]
        assert d["capacity"] - d["booked"] == FALSE_GREEN["inflated_remaining"]

        # 造一条该档候补行，供候补页同态读数
        r = c.post(
            "/api/holds",
            headers=h,
            json={"slot_code": code, "party_key": "P-WAIT-PM", "seats": 9},
        )
        assert r.status_code == 200, r.text
        assert r.json()["disposition"] == "候补"

        # 余席页自身（详情）
        assert d["remaining"] == FALSE_GREEN["expected_remaining"]

        surfaces = _five_surfaces(c, h)
        readings = {k: v.get("remaining") for k, v in surfaces.items()}
        assert readings == {
            "slots": FALSE_GREEN["expected_remaining"],
            "hold": FALSE_GREEN["expected_remaining"],
            "wait": FALSE_GREEN["expected_remaining"],
            "reconcile": FALSE_GREEN["expected_remaining"],
            "audit": FALSE_GREEN["expected_remaining"],
        }, readings


def test_two_person_hold_and_remaining_read_contend():
    """两人同时占位与读余席抢档锁；后到只留争用痕，不写业务。"""
    with TestClient(app) as c:
        admin = _login(c, "admin")
        clerk = _login(c, "clerk")
        code = FALSE_GREEN["slot_code"]

        # 甲已抢到档锁（模拟正在办理）
        r = c.post("/api/locks/acquire", headers=admin, json={"lock_key": f"slot:{code}"})
        assert r.status_code == 200, r.text

        # 乙后到占位：只留争用痕
        r_hold = c.post(
            "/api/holds",
            headers=clerk,
            json={"slot_code": code, "party_key": "P-LATE", "seats": 1},
        )
        assert r_hold.status_code == 409, r_hold.text

        # 乙后到读余席：同样抢档锁失败，只留争用痕
        r_read = c.get(f"/api/slots/{code}", headers=clerk)
        assert r_read.status_code == 409, r_read.text

        # 余席列表读面同样要抢锁
        r_list = c.get("/api/slots", headers=clerk)
        assert r_list.status_code == 409, r_list.text
        r_recon = c.get(f"/api/reconcile/{code}", headers=clerk)
        assert r_recon.status_code == 409, r_recon.text

        cont = c.get("/api/contention", headers=admin).json()["items"]
        mine = [
            x for x in cont
            if x["lock_key"] == f"slot:{code}" and x["actor"] == "clerk"
        ]
        assert len(mine) >= 2, cont

        # 后到不写业务：无乙的占位，余席展示不被后到篡改
        holds = c.get("/api/holds", headers=admin).json()["items"]
        assert not [x for x in holds if x["party_key"] == "P-LATE"]

        c.post("/api/locks/release", headers=admin, json={"lock_key": f"slot:{code}"})
        d = c.get(f"/api/slots/{code}", headers=admin).json()
        assert d["remaining"] == FALSE_GREEN["expected_remaining"]


def test_remaining_writeback_failure_rolls_display_back(monkeypatch):
    """甲路径：同事务重算写回；失败时展示余席滚回旧值。"""
    import hold_svc

    with TestClient(app, raise_server_exceptions=False) as c:
        h = _login(c)
        code = FALSE_GREEN["slot_code"]
        before = c.get(f"/api/slots/{code}", headers=h).json()["remaining"]
        assert before == FALSE_GREEN["expected_remaining"]

        def boom(*_a, **_k):
            raise RuntimeError("inject: 余席写回失败")

        monkeypatch.setattr(hold_svc, "recompute_remaining", boom)
        r = c.post(
            "/api/holds",
            headers=h,
            json={"slot_code": code, "party_key": "P-BOOM", "seats": 1},
        )
        assert r.status_code >= 500

        after = c.get(f"/api/slots/{code}", headers=h).json()["remaining"]
        assert after == before
        holds = c.get("/api/holds", headers=h).json()["items"]
        assert not [x for x in holds if x["party_key"] == "P-BOOM"]


def test_confirm_writeback_failure_rolls_back_business(monkeypatch):
    """确认路径写回失败同样整单回滚：正式册、占位态、展示余席均不变。"""
    import confirm_svc

    with TestClient(app, raise_server_exceptions=False) as c:
        h = _login(c)
        code = FALSE_GREEN["slot_code"]
        hold_id = c.get("/api/holds", headers=h).json()["items"][0]["id"]
        before = c.get(f"/api/slots/{code}", headers=h).json()["remaining"]
        books_before = len(c.get("/api/bookings", headers=h).json()["items"])

        def boom(*_a, **_k):
            raise RuntimeError("inject: 确认写回失败")

        monkeypatch.setattr(confirm_svc, "recompute_remaining", boom)
        r = c.post("/api/bookings/confirm", headers=h, json={"hold_id": hold_id})
        assert r.status_code >= 500

        assert c.get(f"/api/slots/{code}", headers=h).json()["remaining"] == before
        assert len(c.get("/api/bookings", headers=h).json()["items"]) == books_before
        states = {
            x["id"]: x["status"]
            for x in c.get("/api/holds", headers=h).json()["items"]
        }
        assert states[hold_id] == "占位中"
