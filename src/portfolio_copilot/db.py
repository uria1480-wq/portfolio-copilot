"""שכבת מסד נתונים (SQLite) לפרויקט: משתמשים, פרופיל, החזקות והפקדות."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from portfolio_copilot.plan import SavingsPlan
from portfolio_copilot.schemas import InvestorProfile

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

-- הפרופיל נשמר כ-JSON אחד לכל משתמש (הסכמה נשארת ב-Pydantic)
CREATE TABLE IF NOT EXISTS profiles (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data_json   TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS holdings (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol      TEXT NOT NULL,
    quantity    REAL NOT NULL,
    avg_cost    REAL,
    updated_at  TEXT NOT NULL,
    UNIQUE (user_id, symbol)
);

CREATE TABLE IF NOT EXISTS deposits (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount        REAL NOT NULL,
    deposited_at  TEXT NOT NULL,
    note          TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doc_type     TEXT NOT NULL,
    period       TEXT,
    data_json    TEXT NOT NULL,
    uploaded_at  TEXT NOT NULL,
    UNIQUE (user_id, doc_type, period)
);

-- תוכנית החיסכון החודשית של המשתמש (JSON אחד, הסכמה ב-Pydantic)
CREATE TABLE IF NOT EXISTS plans (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data_json   TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- מצב כללי לפי מפתח: תשובות הראיון וההדרכה האחרונה
CREATE TABLE IF NOT EXISTS state (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);

-- היסטוריית אירועי "נכנסה משכורת" וההצעות שניתנו
CREATE TABLE IF NOT EXISTS salary_events (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period      TEXT,
    net         REAL NOT NULL,
    data_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path = "data/portfolio.db"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- משתמשים ---
    def get_or_create_user(self, name: str) -> int:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO users (name, created_at) VALUES (?, ?)", (name, _now())
            )
        row = self.conn.execute("SELECT id FROM users WHERE name = ?", (name,)).fetchone()
        return row["id"]

    # --- פרופיל ---
    def save_profile(self, user_id: int, profile: InvestorProfile) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO profiles (user_id, data_json, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       data_json = excluded.data_json, updated_at = excluded.updated_at""",
                (user_id, profile.model_dump_json(), _now()),
            )

    def load_profile(self, user_id: int) -> InvestorProfile:
        row = self.conn.execute(
            "SELECT data_json FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        return InvestorProfile.model_validate_json(row["data_json"]) if row else InvestorProfile()

    # --- החזקות ---
    def upsert_holding(self, user_id: int, symbol: str, quantity: float, avg_cost: float | None = None) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO holdings (user_id, symbol, quantity, avg_cost, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, symbol) DO UPDATE SET
                       quantity = excluded.quantity, avg_cost = excluded.avg_cost,
                       updated_at = excluded.updated_at""",
                (user_id, symbol.strip().upper(), quantity, avg_cost, _now()),
            )

    def delete_holding(self, user_id: int, symbol: str) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM holdings WHERE user_id = ? AND symbol = ?", (user_id, symbol.strip().upper())
            )

    def list_holdings(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT symbol, quantity, avg_cost FROM holdings WHERE user_id = ? ORDER BY symbol", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- הפקדות ---
    def add_deposit(self, user_id: int, amount: float, note: str | None = None, deposited_at: str | None = None) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO deposits (user_id, amount, deposited_at, note) VALUES (?, ?, ?, ?)",
                (user_id, amount, deposited_at or _now(), note),
            )

    def list_deposits(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT amount, deposited_at, note FROM deposits WHERE user_id = ? ORDER BY deposited_at, id",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def save_document(self, user_id: int, doc: dict) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO documents (user_id, doc_type, period, data_json, uploaded_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, doc_type, period) DO UPDATE SET
                       data_json = excluded.data_json, uploaded_at = excluded.uploaded_at""",
                (user_id, doc["doc_type"], doc.get("period"), json.dumps(doc, ensure_ascii=False), _now()),
            )

    def list_documents(self, user_id: int, doc_type: str | None = None) -> list[dict]:
        sql = "SELECT data_json FROM documents WHERE user_id = ?"
        params: list = [user_id]
        if doc_type:
            sql += " AND doc_type = ?"
            params.append(doc_type)
        rows = self.conn.execute(sql + " ORDER BY period DESC, id DESC", params).fetchall()
        return [json.loads(r["data_json"]) for r in rows]

    # --- תוכנית חודשית ---
    def save_plan(self, user_id: int, plan: SavingsPlan) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO plans (user_id, data_json, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       data_json = excluded.data_json, updated_at = excluded.updated_at""",
                (user_id, plan.model_dump_json(), _now()),
            )

    def load_plan(self, user_id: int) -> SavingsPlan:
        row = self.conn.execute("SELECT data_json FROM plans WHERE user_id = ?", (user_id,)).fetchone()
        return SavingsPlan.model_validate_json(row["data_json"]) if row else SavingsPlan()

    # --- אירועי משכורת ---
    def add_salary_event(self, user_id: int, result: dict) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO salary_events (user_id, period, net, data_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, result.get("period"), result["net"], json.dumps(result, ensure_ascii=False), _now()),
            )

    def list_salary_events(self, user_id: int, limit: int = 12) -> list[dict]:
        rows = self.conn.execute(
            "SELECT data_json FROM salary_events WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
        ).fetchall()
        return [json.loads(r["data_json"]) for r in rows]

    # --- מצב כללי (ראיון, הדרכה) ---
    def save_state(self, user_id: int, key: str, data: dict) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO state (user_id, key, data_json, updated_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id, key) DO UPDATE SET
                       data_json = excluded.data_json, updated_at = excluded.updated_at""",
                (user_id, key, json.dumps(data, ensure_ascii=False), _now()),
            )

    def load_state(self, user_id: int, key: str) -> dict | None:
        row = self.conn.execute(
            "SELECT data_json FROM state WHERE user_id = ? AND key = ?", (user_id, key)
        ).fetchone()
        return json.loads(row["data_json"]) if row else None