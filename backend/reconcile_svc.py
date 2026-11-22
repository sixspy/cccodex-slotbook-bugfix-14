"""对账：档期 booked 与正式册 seats 同源校验，余席扣待确认。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from remaining_svc import (
    pending_seats,
    read_remaining_locked,
    recompute_all,
    recompute_remaining,
)

router = APIRouter(tags=["reconcile"])


@router.get("/api/reconcile")
def reconcile_all(authorization: AuthHeader = None):
    user = require_user(authorization)
    with read_remaining_locked(user) as conn:
        recompute_all(conn)
        conn.commit()
        slots = conn.execute("SELECT * FROM slots ORDER BY code").fetchall()
        items = []
        for s in slots:
            booked_sum = conn.execute(
                """SELECT COALESCE(SUM(seats),0) s FROM bookings
                   WHERE slot_id=? AND status='已确认'""",
                (s["id"],),
            ).fetchone()["s"]
            pending = pending_seats(conn, s["id"])
            ok = int(booked_sum) == int(s["booked"])
            items.append(
                {
                    "slot_code": s["code"],
                    "slot_booked": s["booked"],
                    "booking_seats": booked_sum,
                    "pending_seats": pending,
                    "remaining": s["remaining"],
                    "generation": s["generation"],
                    "ok": ok,
                    "status": s["status"],
                }
            )
        # 余席同态自检：展示余席必须等于容量-已订-待确认
        remaining_ok = all(
            int(i["remaining"]) == max(
                0,
                int(next(s["capacity"] for s in slots if s["code"] == i["slot_code"]))
                - int(i["slot_booked"])
                - int(i["pending_seats"]),
            )
            for i in items
        )
        return {
            "items": items,
            "all_ok": all(i["ok"] for i in items),
            "remaining_ok": remaining_ok,
        }


@router.get("/api/reconcile/{code}")
def reconcile_one(code: str, authorization: AuthHeader = None):
    user = require_user(authorization)
    with read_remaining_locked(user, [code]) as conn:
        s = conn.execute("SELECT * FROM slots WHERE code=?", (code,)).fetchone()
        if not s:
            raise HTTPException(404, "档期不存在")
        booked_sum = conn.execute(
            """SELECT COALESCE(SUM(seats),0) s FROM bookings
               WHERE slot_id=? AND status='已确认'""",
            (s["id"],),
        ).fetchone()["s"]
        holds = conn.execute(
            "SELECT COUNT(*) c FROM holds WHERE slot_id=? AND status='占位中'",
            (s["id"],),
        ).fetchone()["c"]
        pending = pending_seats(conn, s["id"])
        remaining = recompute_remaining(conn, s["id"])
        conn.commit()
        return {
            "slot_code": code,
            "slot_booked": s["booked"],
            "booking_seats": booked_sum,
            "open_holds": holds,
            "pending_seats": pending,
            "ok": int(booked_sum) == int(s["booked"]),
            "remaining_ok": remaining == max(
                0, int(s["capacity"]) - int(s["booked"]) - int(pending)
            ),
            "generation": s["generation"],
            "remaining": remaining,
        }
