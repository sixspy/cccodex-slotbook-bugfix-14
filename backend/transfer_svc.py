"""空桩：跨档迁移（题面 transfer_booking 应对得上）。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth import AuthHeader, require_user, require_writer
from db import connect, write_audit

router = APIRouter(tags=["transfer"])


class TransferIn(BaseModel):
    booking_id: int
    to_slot_code: str
    note: str = ""


@router.get("/api/transfer/jobs")
def list_jobs(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM transfer_jobs ORDER BY id DESC LIMIT 100"
        ).fetchall()
        return {"items": [dict(r) for r in rows], "stub": True}


@router.post("/api/transfer")
def transfer_booking(body: TransferIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        b = conn.execute(
            "SELECT * FROM bookings WHERE id=?", (body.booking_id,)
        ).fetchone()
        if not b:
            raise HTTPException(404, "正式预订不存在")
        slot = conn.execute(
            "SELECT id FROM slots WHERE code=?", (body.to_slot_code,)
        ).fetchone()
        if not slot:
            raise HTTPException(404, "目标档期不存在")
        now = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute(
            """INSERT INTO transfer_jobs(booking_id,to_slot_code,status,note,created_at)
               VALUES (?,?,?,?,?)""",
            (
                body.booking_id,
                body.to_slot_code,
                "空桩未执行",
                body.note or "待实现跨档迁移",
                now,
            ),
        )
        write_audit(
            conn,
            user,
            "transfer_stub",
            str(body.booking_id),
            {"to": body.to_slot_code, "job_id": cur.lastrowid},
        )
        conn.commit()
        return {
            "ok": False,
            "stub": True,
            "job_id": cur.lastrowid,
            "message": "transfer_booking 空桩：尚未实现跨档写路径",
        }
