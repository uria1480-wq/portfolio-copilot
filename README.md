# Portfolio Copilot

סוכן פיננסי אישי מבוסס AI: מכיר את המשקיע בשיחה קצרה, מציג תמונת מצב, מציע הצעה בסוגי נכסים
(קרן חירום, תמהיל להון ולהפקדה, מסלול לפנסיה ולהשתלמות) ומחלק את ההשקעה החודשית. המספרים מחושבים בקוד ולא על ידי המודל, וההחלטה הסופית נשארת אצל המשתמש.

פרויקט אקדמי בקורס "פיתוח פתרונות מבוססי AI". אין כאן ייעוץ השקעות או פנסיה מורשה.

## התקנה

צריך [uv](https://docs.astral.sh/uv/) ו-Git.

```bash
git clone https://github.com/uria1480-wq/portfolio-copilot.git
cd portfolio-copilot
uv sync
```

יוצרים בתיקיית הפרויקט קובץ `.env` עם המשתנים האלה (את המפתח מקבלים בפרטי):

```
OPENAI_API_KEY=<המפתח של Gemini>
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```

הקובץ `.env` והתיקייה `data/` לא עולים ל-git.

## הרצה

```bash
uv run python -m portfolio_copilot.app
```

האפליקציה נפתחת בכתובת http://127.0.0.1:7860.
עם `--fresh` מסד הנתונים נשמר בזיכרון בלבד, וכל הרצה מתחילה נקייה.

## בדיקות

```bash
uv run python -m pytest -q
```

## מבנה

- `src/portfolio_copilot/`: הקוד. הממשק ב-`app.py` וב-`ui.py`, והלוגיקה במודולים האחרים.
- `tests/`: בדיקות.
- `design/`: מסמכי החזון, ה-MVP והמודולים.
- `CLAUDE.md`: כללי העבודה לסוכן הקוד.
