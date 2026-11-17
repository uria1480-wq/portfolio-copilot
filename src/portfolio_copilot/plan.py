"""תוכנית חיסכון חודשית אישית. נגזרת מניתוח המשקיע ומאושרת על ידו, ואז הקוד מריץ אותה בכל משכורת."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Bucket(BaseModel):
    """לאן הולך חלק מהסכום שמופרש: כסף נזיל (קרן חירום, מטרה קרובה) או השקעות."""
    name: str
    kind: Literal["cash", "invest"]
    share: float = Field(ge=0, le=1)


class SavingsPlan(BaseModel):
    monthly_net_income: Optional[float] = Field(default=None, ge=0, description="הכנסה נטו חודשית אופיינית")
    savings_mode: Literal["fixed", "percent"] = Field(default="fixed", description="סכום קבוע בשקלים או אחוז מהנטו")
    savings_value: Optional[float] = Field(default=None, ge=0, description="שקלים, או שבר מהנטו (0.25 הוא 25%)")
    buckets: list[Bucket] = Field(default_factory=lambda: [Bucket(name="השקעות", kind="invest", share=1.0)])
    rationale: Optional[str] = Field(default=None, description="למה התוכנית הזו מתאימה לאדם")
    confirmed: bool = Field(default=False, description="האם המשתמש אישר את התוכנית")

    @model_validator(mode="after")
    def _normalize(self):
        if self.savings_mode == "percent" and self.savings_value is not None:
            if self.savings_value > 1:  # אפשר להזין 25 במקום 0.25
                self.savings_value = round(self.savings_value / 100, 4)
            if self.savings_value > 1:
                raise ValueError("אחוז ההפרשה לא יכול לעלות על 100%")
        total = sum(b.share for b in self.buckets)
        if self.buckets and total > 0 and abs(total - 1) > 1e-6:
            for b in self.buckets:
                b.share = round(b.share / total, 6)
        return self

    def is_ready(self) -> bool:
        """מוכנה להרצה: אושרה, יש סכום הפרשה, ויש לאן לחלק."""
        return bool(self.confirmed and self.savings_value and self.savings_value > 0 and self.buckets)