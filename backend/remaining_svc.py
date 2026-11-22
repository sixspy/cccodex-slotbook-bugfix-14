"""余席同事务重算（BUGFIX-14 甲路径）。

口径：余席 = 容量 - 已订 - 待确认（hold.status='占位中'）。
本模块是余席正确性的唯一写入口：在业务事务内调用、写回 slots.remaining，
调用方失败则事务不提交，展示余席自然滚回旧值。
禁止前端减一，禁止影子表混用（乙路径不采用，见 docs/余席扣待确认说明.md）。
"""
from __future__ import annotations

from contextlib import contextmanager

from fastapi import HTTPException

from locks import release, require_lock


def pending_seats(conn, slot_id: int) -> int:
    """待确认占位席数（占位中）。"""
    return int(
        conn.execute(
            "SELECT COALESCE(SUM(seats),0) s FROM holds "
            "WHERE slot_id=? AND status='占位中'",
            (slot_id,),
        ).fetchone()["s"]
    )


def recompute_remaining(conn, slot_id: int) -> int:
    """同事务重算并写回展示余席，返回重算值。"""
    slot = conn.execute(
        "SELECT capacity, booked FROM slots WHERE id=?", (slot_id,)
    ).fetchone()
    if slot is None:
        raise ValueError(f"档期不存在: {slot_id}")
    pending = pending_seats(conn, slot_id)
    remaining = max(0, int(slot["capacity"]) - int(slot["booked"]) - pending)
    conn.execute(
        "UPDATE slots SET remaining=? WHERE id=?", (remaining, slot_id)
    )
    return remaining


def recompute_all(conn) -> None:
    for row in conn.execute("SELECT id FROM slots").fetchall():
        recompute_remaining(conn, row["id"])


@contextmanager
def read_remaining_locked(user: str, slot_codes: list[str] | None = None):
    """余席读面统一抢档锁：读余席与占位写互斥，后到只留争用痕。

    slot_codes 为空时按库内全部档期加锁（按编码排序，避免死锁）。
    任一把被占即抛 409（争用痕已由 require_lock 落库）。
    """
    from db import connect

    with connect() as conn:
        codes = slot_codes
        if codes is None:
            codes = [
                r["code"]
                for r in conn.execute("SELECT code FROM slots ORDER BY code").fetchall()
            ]
        acquired: list[str] = []
        try:
            for code in sorted(set(codes)):
                lock_key = f"slot:{code}"
                require_lock(conn, lock_key, user)
                acquired.append(lock_key)
            yield conn
        except HTTPException:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            for lock_key in acquired:
                release(conn, lock_key, user)
            conn.commit()
