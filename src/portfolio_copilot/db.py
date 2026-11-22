"""שכבת מסד נתונים (SQLite): משתמשים, פרופיל, תלושים שהועלו ודיווחים חודשיים."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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

-- holdings, deposits, plans, state: טבלאות מגרסאות קודמות. לא בשימוש, ונשארות כדי לא לשנות מסד קיים
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

-- תלושים שהועלו בדיווח החודשי (רק המספרים שחולצו, לא הקובץ)
CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doc_type     TEXT NOT NULL,
    period       TEXT,
    data_json    TEXT NOT NULL,
    uploaded_at  TEXT NOT NULL,
    UNIQUE (user_id, doc_type, period)
);

CREATE TABLE IF NOT EXISTS plans (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data_json   TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS state (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);

-- היסטוריית הדיווחים החודשיים (MonthlyReport כ-JSON)
CREATE TABLE IF NOT EXISTS salary_events (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period      TEXT,
    net         REAL NOT NULL,
    data_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


ALL_HISTORY = -1  # SQLite: LIMIT -1 הוא בלי הגבלה. קרן החירום והדשבורד סופרים את כל הדיווחים


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

    # --- מסמכים ---
    def save_document(self, user_id: int, doc: dict) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO documents (user_id, doc_type, period, data_json, uploaded_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, doc_type, period) DO UPDATE SET
                       data_json = excluded.data_json, uploaded_at = excluded.uploaded_at""",
                (user_id, doc["doc_type"], doc.get("period"), json.dumps(doc, ensure_ascii=False), _now()),
            )

    # --- דיווחים חודשיים ---
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
