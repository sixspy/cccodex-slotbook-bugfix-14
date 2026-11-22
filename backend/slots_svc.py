"""档期盘：开档、关档、容量查询。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth import AuthHeader, require_user, require_writer
from db import connect, write_audit
from locks import release, require_lock
from remaining_svc import read_remaining_locked, recompute_all, recompute_remaining

router = APIRouter(tags=["slots"])


class SlotIn(BaseModel):
    code: str
    title: str
    start_at: str
    end_at: str
    capacity: int = Field(ge=1, le=500)


class CloseIn(BaseModel):
    code: str


@router.get("/api/slots")
def list_slots(authorization: AuthHeader = None):
    user = require_user(authorization)
    with read_remaining_locked(user) as conn:
        recompute_all(conn)
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM slots ORDER BY start_at, code"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/api/slots/{code}")
def get_slot(code: str, authorization: AuthHeader = None):
    user = require_user(authorization)
    with read_remaining_locked(user, [code]) as conn:
        row = conn.execute("SELECT * FROM slots WHERE code=?", (code,)).fetchone()
        if not row:
            raise HTTPException(404, "档期不存在")
        recompute_remaining(conn, row["id"])
        conn.commit()
        return dict(
            conn.execute("SELECT * FROM slots WHERE code=?", (code,)).fetchone()
        )


@router.post("/api/slots")
def create_slot(body: SlotIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        require_lock(conn, f"slot:{body.code}", user)
        try:
            exists = conn.execute(
                "SELECT id FROM slots WHERE code=?", (body.code,)
            ).fetchone()
            if exists:
                raise HTTPException(409, "档期编码已存在")
            if body.end_at <= body.start_at:
                raise HTTPException(400, "结束时间必须晚于开始")
            conn.execute(
                """INSERT INTO slots(code,title,start_at,end_at,capacity,booked,status,generation)
                   VALUES (?,?,?,?,?,0,'开放',1)""",
                (body.code, body.title, body.start_at, body.end_at, body.capacity),
            )
            new_id = conn.execute(
                "SELECT id FROM slots WHERE code=?", (body.code,)
            ).fetchone()["id"]
            recompute_remaining(conn, new_id)
            write_audit(conn, user, "slot_create", body.code, body.model_dump())
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            release(conn, f"slot:{body.code}", user)
            conn.commit()
    return {"ok": True, "code": body.code}


@router.post("/api/slots/close")
def close_slot(body: CloseIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        require_lock(conn, f"slot:{body.code}", user)
        try:
            row = conn.execute(
                "SELECT * FROM slots WHERE code=?", (body.code,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "档期不存在")
            if row["status"] == "关闭":
                raise HTTPException(409, "档期已关闭")
            open_holds = conn.execute(
                "SELECT COUNT(*) c FROM holds WHERE slot_id=? AND status='占位中'",
                (row["id"],),
            ).fetchone()["c"]
            if open_holds:
                raise HTTPException(409, "仍有未确认占位，禁止关档")
            conn.execute(
                "UPDATE slots SET status='关闭' WHERE id=?", (row["id"],)
            )
            write_audit(conn, user, "slot_close", body.code, {"generation": row["generation"]})
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            release(conn, f"slot:{body.code}", user)
            conn.commit()
    return {"ok": True}


@router.get("/api/dashboard")
def dashboard(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        return {
            "slots_open": conn.execute(
                "SELECT COUNT(*) c FROM slots WHERE status='开放'"
            ).fetchone()["c"],
            "holds_open": conn.execute(
                "SELECT COUNT(*) c FROM holds WHERE status='占位中'"
            ).fetchone()["c"],
            "bookings": conn.execute(
                "SELECT COUNT(*) c FROM bookings WHERE status='已确认'"
            ).fetchone()["c"],
            "waitlist": conn.execute(
                "SELECT COUNT(*) c FROM waitlist WHERE status='候补中'"
            ).fetchone()["c"],
            "now": datetime.now().isoformat(timespec="seconds"),
        }
