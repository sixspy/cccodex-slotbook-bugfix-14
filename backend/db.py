"""SQLite：档期预订母仓公共库层。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB_PATH = DATA / "app.db"
FIXTURES = ROOT / "fixtures"
FRONTEND = ROOT / "frontend"

PRODUCT_META = {
    "modules": [
        "slots",
        "holds",
        "bookings",
        "waitlist",
        "reconcile",
        "locks",
        "audit",
        "release",
        "transfer",
    ],
    "stubs": ["release_slot", "transfer_booking"],
}


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def sha_password(password: str) -> str:
    import hashlib

    return hashlib.sha256(password.encode("utf-8")).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  username TEXT PRIMARY KEY,
  password_sha TEXT NOT NULL,
  role TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS slots(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  capacity INTEGER NOT NULL,
  booked INTEGER NOT NULL DEFAULT 0,
  remaining INTEGER,
  status TEXT NOT NULL,
  generation INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS holds(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slot_id INTEGER NOT NULL,
  party_key TEXT NOT NULL,
  seats INTEGER NOT NULL,
  status TEXT NOT NULL,
  expire_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(slot_id) REFERENCES slots(id)
);
CREATE TABLE IF NOT EXISTS bookings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slot_id INTEGER NOT NULL,
  hold_id INTEGER,
  party_key TEXT NOT NULL,
  seats INTEGER NOT NULL,
  snapshot_gen INTEGER NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS waitlist(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slot_id INTEGER NOT NULL,
  party_key TEXT NOT NULL,
  seats INTEGER NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS slot_locks(
  lock_key TEXT PRIMARY KEY,
  holder TEXT NOT NULL,
  acquired_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contention_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lock_key TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_trail(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT NOT NULL,
  payload TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS release_jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  booking_id INTEGER,
  status TEXT NOT NULL,
  note TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transfer_jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  booking_id INTEGER,
  to_slot_code TEXT,
  status TEXT NOT NULL,
  note TEXT,
  created_at TEXT NOT NULL
);
"""


def write_audit(conn, actor: str, action: str, target: str, payload: dict | None = None) -> None:
    from datetime import datetime

    conn.execute(
        "INSERT INTO audit_trail(actor,action,target,payload,created_at) VALUES (?,?,?,?,?)",
        (
            actor,
            action,
            target,
            json.dumps(payload or {}, ensure_ascii=False),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def ensure_users(conn) -> None:
    for u, p, role in (
        ("admin", "123456", "管理员"),
        ("clerk", "123456", "文员"),
        ("viewer", "123456", "只读"),
    ):
        conn.execute(
            "INSERT OR IGNORE INTO users(username,password_sha,role) VALUES (?,?,?)",
            (u, sha_password(p), role),
        )


def seed_if_empty(conn) -> None:
    n = conn.execute("SELECT COUNT(*) c FROM slots").fetchone()["c"]
    if n:
        return
    slots_path = FIXTURES / "slots.json"
    holds_path = FIXTURES / "holds.json"
    slots = json.loads(slots_path.read_text(encoding="utf-8")) if slots_path.is_file() else []
    holds = json.loads(holds_path.read_text(encoding="utf-8")) if holds_path.is_file() else []
    for s in slots:
        conn.execute(
            """INSERT INTO slots(code,title,start_at,end_at,capacity,booked,status,generation)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                s["code"],
                s["title"],
                s["start_at"],
                s["end_at"],
                s["capacity"],
                s.get("booked", 0),
                s["status"],
                s.get("generation", 1),
            ),
        )
    for h in holds:
        slot = conn.execute("SELECT id FROM slots WHERE code=?", (h["slot_code"],)).fetchone()
        if not slot:
            continue
        conn.execute(
            """INSERT INTO holds(slot_id,party_key,seats,status,expire_at,created_at)
               VALUES (?,?,?,?,?,?)""",
            (
                slot["id"],
                h["party_key"],
                h["seats"],
                h["status"],
                h["expire_at"],
                h["created_at"],
            ),
        )
    # 一笔已确认正式册，便于对账种子
    s1 = conn.execute("SELECT id,generation FROM slots WHERE code='S-AM-01'").fetchone()
    if s1:
        conn.execute(
            """INSERT INTO bookings(slot_id,hold_id,party_key,seats,snapshot_gen,status,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (s1["id"], None, "P-SEED", 2, s1["generation"], "已确认", "2026-11-20T09:00:00"),
        )
        conn.execute(
            "UPDATE slots SET booked = booked + 2 WHERE id=?", (s1["id"],)
        )
    conn.execute(
        "INSERT INTO waitlist(slot_id,party_key,seats,reason,status,created_at) VALUES (?,?,?,?,?,?)",
        (s1["id"] if s1 else 1, "P-WAIT", 1, "容量不足", "候补中", "2026-11-20T09:05:00"),
    )
    write_audit(conn, "system", "seed", "slots", {"count": len(slots)})


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        ensure_users(conn)
        seed_if_empty(conn)
        _recompute_all(conn)
        conn.commit()


def _migrate(conn) -> None:
    """BUGFIX-14：老库补 remaining 展示列。"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(slots)").fetchall()}
    if "remaining" not in cols:
        conn.execute("ALTER TABLE slots ADD COLUMN remaining INTEGER")


def _recompute_all(conn) -> None:
    """按余席同事务重算口径回填展示余席（扣待确认）。"""
    from remaining_svc import recompute_remaining

    for row in conn.execute("SELECT id FROM slots").fetchall():
        recompute_remaining(conn, row["id"])
