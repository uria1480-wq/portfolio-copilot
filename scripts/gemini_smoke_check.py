import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)

print("שולח פנייה למודל המדויק מהרשימה...")

# נשתמש במודל המדויק שהופיע ברשימה שלך ובהנחיות המרצה
model_id = "models/gemini-3.5-flash-lite"

response = client.chat.completions.create(
    model=model_id,
    messages=[
        {"role": "system", "content": "You are a helpful financial assistant."},
        {"role": "user", "content": "במשפט אחד: מה זה איזון תיק השקעות (Portfolio Rebalancing)?"}
    ]
)

print("\n--- הצלחה! תשובת המודל: ---")
print(response.choices[0].message.content)