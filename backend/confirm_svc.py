"""确认入册：占位 → 正式预订，写快照 generation。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth import AuthHeader, require_user, require_writer
from db import connect, write_audit
from locks import release, require_lock
from remaining_svc import recompute_remaining

router = APIRouter(tags=["confirm"])


class ConfirmIn(BaseModel):
    hold_id: int


@router.get("/api/bookings")
def list_bookings(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT b.*, s.code AS slot_code FROM bookings b
               JOIN slots s ON s.id=b.slot_id ORDER BY b.id DESC LIMIT 200"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/bookings/confirm")
def confirm_hold(body: ConfirmIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        hold = conn.execute("SELECT * FROM holds WHERE id=?", (body.hold_id,)).fetchone()
        if not hold:
            raise HTTPException(404, "占位不存在")
        slot = conn.execute("SELECT * FROM slots WHERE id=?", (hold["slot_id"],)).fetchone()
        if not slot:
            raise HTTPException(404, "档期不存在")
        lock_key = f"slot:{slot['code']}"
        require_lock(conn, lock_key, user)
        try:
            hold = conn.execute("SELECT * FROM holds WHERE id=?", (body.hold_id,)).fetchone()
            if hold["status"] != "占位中":
                raise HTTPException(409, "占位已非占位中，禁止确认")
            if hold["expire_at"] < datetime.now().isoformat(timespec="seconds"):
                conn.execute(
                    "UPDATE holds SET status='已过期' WHERE id=?", (hold["id"],)
                )
                write_audit(conn, user, "hold_expire", str(hold["id"]), {})
                recompute_remaining(conn, slot["id"])
                conn.commit()
                raise HTTPException(409, "占位已过期")
            # 已订 + 自身待确认已由本单占用，仅需校验其余待确认不超额
            others = conn.execute(
                "SELECT COALESCE(SUM(seats),0) s FROM holds "
                "WHERE slot_id=? AND status='占位中' AND id<>?",
                (slot["id"], hold["id"]),
            ).fetchone()["s"]
            if (
                int(slot["capacity"])
                - int(slot["booked"])
                - int(others)
                < int(hold["seats"])
            ):
                raise HTTPException(409, "确认时容量不足，请释放或改候补")
            now = datetime.now().isoformat(timespec="seconds")
            cur = conn.execute(
                """INSERT INTO bookings(slot_id,hold_id,party_key,seats,snapshot_gen,status,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    slot["id"],
                    hold["id"],
                    hold["party_key"],
                    hold["seats"],
                    slot["generation"],
                    "已确认",
                    now,
                ),
            )
            conn.execute(
                "UPDATE holds SET status='已确认' WHERE id=?", (hold["id"],)
            )
            conn.execute(
                "UPDATE slots SET booked = booked + ? WHERE id=?",
                (hold["seats"], slot["id"]),
            )
            write_audit(
                conn,
                user,
                "booking_confirm",
                hold["party_key"],
                {"booking_id": cur.lastrowid, "gen": slot["generation"]},
            )
            remaining = recompute_remaining(conn, slot["id"])
            conn.commit()
            return {
                "ok": True,
                "booking_id": cur.lastrowid,
                "snapshot_gen": slot["generation"],
                "remaining": remaining,
            }
        except HTTPException:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            release(conn, lock_key, user)
            conn.commit()
