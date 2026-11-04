from datetime import date
from pydantic import BaseModel, EmailStr, model_validator

class UserSignup(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class InvestmentCreate(BaseModel):
    name: str
    category: str  # "market" or "policy"
    invested_amount: float

    # market-category fields (all optional - only relevant when category="market")
    investment_type: str | None = None
    scheme_code: str | None = None
    units: float | None = None
    purchase_date: date | None = None

    # policy-category fields. start_date is REQUIRED for category="policy"
    # (validated in the model validator below) because the reality-check
    # calculation reconstructs the premium history from it. The DB column
    # itself stays nullable so pre-existing rows keep working.
    start_date: date | None = None
    premium_amount: float | None = None
    premium_frequency: str | None = None
    next_due_date: date | None = None
    maturity_date: date | None = None
    maturity_value: float | None = None

    @model_validator(mode="after")
    def require_start_date_for_policy(self):
        # A policy without a start date can't have its premium history
        # reconstructed (reality check), so require it up front for NEW
        # policy rows. Market rows and updates are untouched.
        if self.category == "policy" and self.start_date is None:
            raise ValueError("start_date is required for policy investments")
        return self


class InvestmentUpdate(BaseModel):
    # Every field is optional here, unlike InvestmentCreate. This lets the
    # frontend send just the fields that changed (e.g. only next_due_date
    # after a payment) instead of having to resend the entire object.
    name: str | None = None
    start_date: date | None = None
    invested_amount: float | None = None
    investment_type: str | None = None
    scheme_code: str | None = None
    units: float | None = None
    purchase_date: date | None = None
    premium_amount: float | None = None
    premium_frequency: str | None = None
    next_due_date: date | None = None
    maturity_date: date | None = None
    maturity_value: float | None = None