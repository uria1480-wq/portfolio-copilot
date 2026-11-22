"""הרצה מול Gemini אמיתי, באותו מסלול כמו האפליקציה: agent.chat_step עם Store בזיכרון.

כדי לראות אילו כלים נקראו ומה הם החזירו, עוטפים את agent.run_profile_tool ו-agent.run_tool (בלי לשנות קוד).
גם client.chat.completions.create נעטף, כדי לספור קריאות ל-LLM. שום דבר לא נכתב ל-data/.
"""
import contextlib
import io
import time
from dataclasses import dataclass, field
from datetime import date

from portfolio_copilot import agent
from portfolio_copilot.db import Store
from portfolio_copilot.schemas import InvestorProfile

ERROR_PREFIX = "שגיאה בתקשורת עם הסוכן"


@dataclass
class ToolCall:
    name: str
    args: dict
    result: dict


@dataclass
class Turn:
    reply: str
    profile: InvestorProfile
    calls: list[ToolCall] = field(default_factory=list)
    llm_calls: int = 0
    seconds: float = 0.0
    error: str | None = None

    @property
    def tool_names(self) -> list[str]:
        return [c.name for c in self.calls]


class Recorder:
    """עוטף את הכלים ואת הקריאה למודל, ומחזיר אותם למצב המקורי ביציאה."""

    def __init__(self):
        self.calls: list[ToolCall] = []
        self.llm_calls = 0

    def __enter__(self):
        self._profile_tool, self._tool = agent.run_profile_tool, agent.run_tool
        completions = agent.client.chat.completions
        self._create = completions.create

        def profile_tool(name, args, profile, today=None, user_message=None):
            result, new_profile = self._profile_tool(name, args, profile, today, user_message)
            self.calls.append(ToolCall(name, dict(args or {}), result))
            return result, new_profile

        def tool(name, args, store, user_id, profile, today=None):
            result = self._tool(name, args, store, user_id, profile, today)
            self.calls.append(ToolCall(name, dict(args or {}), result))
            return result

        def create(**kwargs):
            self.llm_calls += 1
            return self._create(**kwargs)

        agent.run_profile_tool, agent.run_tool = profile_tool, tool
        completions.create = create
        return self

    def __exit__(self, *exc):
        agent.run_profile_tool, agent.run_tool = self._profile_tool, self._tool
        agent.client.chat.completions.create = self._create
        return False


RATE_LIMIT_WAITS = (30, 60, 90)  # שניות המתנה לפני ניסיון חוזר אחרי 429 (מגבלת קצב) או 5xx (תקלה זמנית בשרת)
RETRYABLE = ("429", "500", "502", "503", "504")


def _retryable(error: str | None) -> bool:
    return bool(error) and any(f"Error code: {code}" in error for code in RETRYABLE)


def run_turn(history: list[dict], profile: InvestorProfile, today: date | None = None,
             salary_events: list[dict] | None = None) -> Turn:
    """תור אחד מול Gemini אמיתי. אחרי 429 או 5xx מחכה (RATE_LIMIT_WAITS) ומנסה שוב.
    קריאות ל-LLM נספרות בכל הניסיונות."""
    llm_calls = 0
    for wait in (*RATE_LIMIT_WAITS, None):
        turn = _run_turn_once(history, profile, today, salary_events)
        llm_calls += turn.llm_calls
        if not _retryable(turn.error) or wait is None:
            break
        print(f"  [{turn.error[-3:]}: מחכה {wait} שניות ומנסה שוב]", flush=True)
        time.sleep(wait)
    turn.llm_calls = llm_calls
    return turn


def _run_turn_once(history, profile, today, salary_events) -> Turn:
    store = Store(":memory:")
    user_id = store.get_or_create_user("eval")
    store.save_profile(user_id, profile)
    for event in salary_events or []:
        store.add_salary_event(user_id, event)
    started = time.perf_counter()
    with Recorder() as rec, contextlib.redirect_stdout(io.StringIO()):
        reply, new_profile = agent.chat_step(list(history), profile, store, user_id, today)
    turn = Turn(reply=reply, profile=new_profile, calls=rec.calls, llm_calls=rec.llm_calls,
                seconds=time.perf_counter() - started)
    if reply.startswith(ERROR_PREFIX):
        turn.error = reply
    return turn


def model_name() -> str:
    return agent.MODEL_NAME
