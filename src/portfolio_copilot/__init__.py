from pydantic import BaseModel, Field
from bidi.algorithm import get_display

def bidi_text(text: str) -> str:
    """הופך את הטקסט כדי שיוצג ישר בטרמינל של ווינדוס"""
    return get_display(text)

# 1. הגדרת המודלים
class AssetTarget(BaseModel):
    ticker: str
    target_weight: float = Field(gt=0, le=1.0, description="משקל הנכס בין 0 ל-1")

class DepositPlanRequest(BaseModel):
    deposit_amount: float = Field(gt=0, description="סכום הפקדה חיובי")
    targets: list[AssetTarget]

class AllocationResult(BaseModel):
    allocations: dict[str, float]
    total_allocated: float

# 2. לוגיקת החישוב (Mock)
def calculate_mock_allocation(request: DepositPlanRequest) -> AllocationResult:
    allocations = {}
    total = 0.0
    for item in request.targets:
        allocated_amount = round(request.deposit_amount * item.target_weight, 2)
        allocations[item.ticker] = allocated_amount
        total += allocated_amount
    return AllocationResult(allocations=allocations, total_allocated=total)

def main() -> None:
    print(bidi_text("--- Portfolio Copilot: הרצת תרחיש ראשון (Thin Slice) ---"))
    
    sample_request = DepositPlanRequest(
        deposit_amount=5000.0,
        targets=[
            AssetTarget(ticker="S&P 500 ETF", target_weight=0.8),
            AssetTarget(ticker="BOND ETF", target_weight=0.2)
        ]
    )
    
    result = calculate_mock_allocation(sample_request)
    
    print(bidi_text(f"סכום להפקדה: {sample_request.deposit_amount:,.2f} ₪"))
    print(bidi_text("חלוקת רכישה מוצעת:"))
    for ticker, amount in result.allocations.items():
        print(f"  - {ticker}: {amount:,.2f} ₪")
    print(bidi_text(f"סה\"כ הוקצה: {result.total_allocated:,.2f} ₪"))

if __name__ == "__main__":
    main()