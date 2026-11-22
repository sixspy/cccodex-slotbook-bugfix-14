"""审计与互证只读面。"""
from __future__ import annotations

from fastapi import APIRouter

from auth import AuthHeader, require_user
from db import connect
from remaining_svc import read_remaining_locked, recompute_all

router = APIRouter(tags=["audit"])


@router.get("/api/audit")
def list_audit(authorization: AuthHeader = None, limit: int = 100):
    user = require_user(authorization)
    lim = max(1, min(limit, 500))
    with read_remaining_locked(user) as conn:
        recompute_all(conn)
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM audit_trail ORDER BY id DESC LIMIT ?", (lim,)
        ).fetchall()
        remaining = conn.execute(
            "SELECT code AS slot_code, capacity, booked, remaining, status "
            "FROM slots ORDER BY code"
        ).fetchall()
        return {
            "items": [dict(r) for r in rows],
            # 审计页余席读面：与档期行写回值同源
            "remaining": [dict(r) for r in remaining],
        }


@router.get("/api/proof/{party_key}")
def proof(party_key: str, authorization: AuthHeader = None):
    """按当事人互证：占位/正式/候补是否同源可读。"""
    require_user(authorization)
    with connect() as conn:
        holds = conn.execute(
            "SELECT * FROM holds WHERE party_key=? ORDER BY id DESC", (party_key,)
        ).fetchall()
        books = conn.execute(
            "SELECT * FROM bookings WHERE party_key=? ORDER BY id DESC", (party_key,)
        ).fetchall()
        waits = conn.execute(
            "SELECT * FROM waitlist WHERE party_key=? ORDER BY id DESC", (party_key,)
        ).fetchall()
        return {
            "party_key": party_key,
            "holds": [dict(r) for r in holds],
            "bookings": [dict(r) for r in books],
            "waitlist": [dict(r) for r in waits],
        }
