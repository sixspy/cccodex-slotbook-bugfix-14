"""空桩：正式册释放/重开（题面 release_slot 应对得上）。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth import AuthHeader, require_user, require_writer
from db import connect, write_audit

router = APIRouter(tags=["release"])


class ReleaseIn(BaseModel):
    booking_id: int
    note: str = ""


@router.get("/api/release/jobs")
def list_jobs(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM release_jobs ORDER BY id DESC LIMIT 100"
        ).fetchall()
        return {"items": [dict(r) for r in rows], "stub": True}


@router.post("/api/release")
def release_booking(body: ReleaseIn, authorization: AuthHeader = None):
    """空桩：只登记任务与审计，不改 bookings/slots（留给功能题实现）。"""
    user = require_writer(authorization)
    with connect() as conn:
        b = conn.execute(
            "SELECT * FROM bookings WHERE id=?", (body.booking_id,)
        ).fetchone()
        if not b:
            raise HTTPException(404, "正式预订不存在")
        now = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute(
            """INSERT INTO release_jobs(booking_id,status,note,created_at)
               VALUES (?,?,?,?)""",
            (body.booking_id, "空桩未执行", body.note or "待实现释放路径", now),
        )
        write_audit(
            conn,
            user,
            "release_stub",
            str(body.booking_id),
            {"job_id": cur.lastrowid},
        )
        conn.commit()
        return {
            "ok": False,
            "stub": True,
            "job_id": cur.lastrowid,
            "message": "release_slot 空桩：尚未实现正式册释放写路径",
        }
