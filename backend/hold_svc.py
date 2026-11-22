"""占位：容量校验、并发锁、候补分流。"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth import AuthHeader, require_user, require_writer
from db import connect, write_audit
from locks import release, require_lock
from remaining_svc import pending_seats, read_remaining_locked, recompute_remaining

router = APIRouter(tags=["holds"])


class HoldIn(BaseModel):
    slot_code: str
    party_key: str
    seats: int = Field(ge=1, le=50)


@router.get("/api/holds")
def list_holds(authorization: AuthHeader = None):
    user = require_user(authorization)
    with read_remaining_locked(user) as conn:
        rows = conn.execute(
            """SELECT h.*, s.code AS slot_code, s.title AS slot_title,
                      s.capacity AS slot_capacity, s.booked AS slot_booked,
                      s.remaining AS remaining
               FROM holds h JOIN slots s ON s.id=h.slot_id
               ORDER BY h.id DESC LIMIT 200"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/holds")
def create_hold(body: HoldIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    lock_key = f"slot:{body.slot_code}"
    with connect() as conn:
        require_lock(conn, lock_key, user)
        try:
            slot = conn.execute(
                "SELECT * FROM slots WHERE code=?", (body.slot_code,)
            ).fetchone()
            if not slot:
                raise HTTPException(404, "档期不存在")
            if slot["status"] != "开放":
                raise HTTPException(409, "档期未开放，禁止占位")
            pending = pending_seats(conn, slot["id"])
            free = int(slot["capacity"]) - int(slot["booked"]) - pending
            now = datetime.now().isoformat(timespec="seconds")
            expire = (datetime.now() + timedelta(minutes=30)).isoformat(timespec="seconds")
            if body.seats > free:
                conn.execute(
                    """INSERT INTO waitlist(slot_id,party_key,seats,reason,status,created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (slot["id"], body.party_key, body.seats, "容量不足", "候补中", now),
                )
                write_audit(
                    conn,
                    user,
                    "hold_to_waitlist",
                    body.party_key,
                    {"slot": body.slot_code, "free": free, "want": body.seats},
                )
                recompute_remaining(conn, slot["id"])
                conn.commit()
                return {"disposition": "候补", "free": free}
            conn.execute(
                """INSERT INTO holds(slot_id,party_key,seats,status,expire_at,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (slot["id"], body.party_key, body.seats, "占位中", expire, now),
            )
            hold_id = conn.execute("SELECT last_insert_rowid() i").fetchone()["i"]
            write_audit(
                conn,
                user,
                "hold_create",
                body.party_key,
                {"slot": body.slot_code, "seats": body.seats, "hold_id": hold_id},
            )
            remaining = recompute_remaining(conn, slot["id"])
            conn.commit()
            return {
                "disposition": "占位",
                "hold_id": hold_id,
                "expire_at": expire,
                "remaining": remaining,
            }
        except HTTPException:
            conn.rollback()
            raise
        except Exception:
            # 甲路径：重算/写回失败 → 整个业务事务回滚，展示余席滚回旧值
            conn.rollback()
            raise
        finally:
            release(conn, lock_key, user)
            conn.commit()
