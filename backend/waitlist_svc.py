"""候补队列：列表、取消、手工晋升探测。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth import AuthHeader, require_user, require_writer
from db import connect, write_audit
from locks import release, require_lock

router = APIRouter(tags=["waitlist"])


class CancelIn(BaseModel):
    wait_id: int


class PromoteIn(BaseModel):
    wait_id: int


@router.get("/api/waitlist")
def list_wait(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT w.*, s.code AS slot_code FROM waitlist w
               JOIN slots s ON s.id=w.slot_id ORDER BY w.id DESC LIMIT 200"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/waitlist/cancel")
def cancel_wait(body: CancelIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        row = conn.execute("SELECT * FROM waitlist WHERE id=?", (body.wait_id,)).fetchone()
        if not row:
            raise HTTPException(404, "候补不存在")
        if row["status"] != "候补中":
            raise HTTPException(409, "候补状态不可取消")
        conn.execute(
            "UPDATE waitlist SET status='已取消' WHERE id=?", (body.wait_id,)
        )
        write_audit(conn, user, "waitlist_cancel", str(body.wait_id), {})
        conn.commit()
    return {"ok": True}


@router.post("/api/waitlist/promote")
def promote_wait(body: PromoteIn, authorization: AuthHeader = None):
    """有空位时把候补转成占位（仍须再确认才入正式册）。"""
    user = require_writer(authorization)
    with connect() as conn:
        wrow = conn.execute("SELECT * FROM waitlist WHERE id=?", (body.wait_id,)).fetchone()
        if not wrow:
            raise HTTPException(404, "候补不存在")
        slot = conn.execute("SELECT * FROM slots WHERE id=?", (wrow["slot_id"],)).fetchone()
        lock_key = f"slot:{slot['code']}"
        require_lock(conn, lock_key, user)
        try:
            if wrow["status"] != "候补中":
                raise HTTPException(409, "候补非候补中")
            pending = conn.execute(
                "SELECT COALESCE(SUM(seats),0) s FROM holds WHERE slot_id=? AND status='占位中'",
                (slot["id"],),
            ).fetchone()["s"]
            free = int(slot["capacity"]) - int(slot["booked"]) - int(pending)
            if wrow["seats"] > free:
                raise HTTPException(409, "仍无足够空位，禁止晋升")
            now = datetime.now().isoformat(timespec="seconds")
            expire = datetime.now().isoformat(timespec="seconds")
            from datetime import timedelta

            expire = (datetime.now() + timedelta(minutes=30)).isoformat(timespec="seconds")
            cur = conn.execute(
                """INSERT INTO holds(slot_id,party_key,seats,status,expire_at,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (slot["id"], wrow["party_key"], wrow["seats"], "占位中", expire, now),
            )
            conn.execute(
                "UPDATE waitlist SET status='已晋升' WHERE id=?", (body.wait_id,)
            )
            write_audit(
                conn,
                user,
                "waitlist_promote",
                wrow["party_key"],
                {"hold_id": cur.lastrowid},
            )
            conn.commit()
            return {"ok": True, "hold_id": cur.lastrowid}
        finally:
            release(conn, lock_key, user)
            conn.commit()
