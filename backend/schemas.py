import datetime as dt
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, model_validator, field_validator, ConfigDict

class UserSignup(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Enforce password policy on signup:
        - At least 8 characters
        - Not entirely numeric
        - At most 72 UTF-8 bytes (prevents bcrypt 5.0.0 crash / HTTP 500)
        """
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if v.isdigit():
            raise ValueError("Password cannot be entirely numeric")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 bytes")
        return v

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


# ---------------------------------------------------------------------------
# Account Schemas (Phase 6)
# ---------------------------------------------------------------------------

class AccountCreate(BaseModel):
    name: str
    account_type: str = "savings"  # savings, checking, credit_card, wallet, investment, imported, other
    currency: str = "INR"
    opening_balance: Decimal = Decimal("0.00")
    masked_identifier: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Account name cannot be empty")
        return s


class AccountUpdate(BaseModel):
    name: str | None = None
    account_type: str | None = None
    currency: str | None = None
    opening_balance: Decimal | None = None
    masked_identifier: str | None = None


class AccountReconcile(BaseModel):
    """Workflow to convert an unreconciled imported account into a verified account
    or merge its transactions into an existing verified account.
    """
    name: str | None = None
    account_type: str = "savings"
    masked_identifier: str | None = None
    merge_into_account_id: int | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    account_type: str
    currency: str
    opening_balance: Decimal
    calculated_balance: Decimal | None = None
    masked_identifier: str | None = None
    is_archived: bool
    is_reconciled: bool
    transaction_count: int = 0
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Category Schemas (Phase 6)
# ---------------------------------------------------------------------------

class CategoryCreate(BaseModel):
    name: str
    category_type: str = "expense"  # expense, income, transfer, investment
    icon: str | None = None
    color: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Category name cannot be empty")
        return s

    @field_validator("category_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid_types = ("expense", "income", "transfer", "investment")
        if v.lower() not in valid_types:
            raise ValueError(f"category_type must be one of {valid_types}")
        return v.lower()


class CategoryUpdate(BaseModel):
    name: str | None = None
    category_type: str | None = None
    icon: str | None = None
    color: str | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    name: str
    category_type: str
    is_system: bool
    icon: str | None = None
    color: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Transaction Schemas (Phase 6)
# ---------------------------------------------------------------------------

class TransactionCreate(BaseModel):
    account_id: int | None = None
    date: dt.date
    value_date: dt.date | None = None
    description: str
    merchant: str | None = None
    amount: Decimal
    type: str  # debit or credit
    classification: str | None = None  # expense, income, transfer, investment
    category_id: int | None = None
    category: str | None = None
    ref_no: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("Amount must be greater than zero")
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        v_lower = v.lower().strip()
        if v_lower not in ("debit", "credit"):
            raise ValueError("Type must be 'debit' or 'credit'")
        return v_lower


class TransferCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    date: dt.date
    amount: Decimal
    description: str | None = "Account Transfer"
    ref_no: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("Amount must be greater than zero")
        return v

    @model_validator(mode="after")
    def validate_different_accounts(self):
        if self.from_account_id == self.to_account_id:
            raise ValueError("Source and destination accounts must be different")
        return self


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    date: dt.date | None = None
    value_date: dt.date | None = None
    description: str | None = None
    merchant: str | None = None
    amount: Decimal | None = None
    type: str | None = None
    classification: str | None = None
    category_id: int | None = None
    category: str | None = None
    ref_no: str | None = None


class CategoryCorrection(BaseModel):
    category_id: int | None = None
    category_name: str | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    account_id: int | None
    statement_id: int | None
    source_row_index: int | None
    date: dt.date
    value_date: dt.date | None
    description: str
    merchant: str | None
    amount: Decimal
    type: str
    classification: str
    category_id: int | None
    category: str
    ref_no: str | None
    balance: Decimal | None
    transaction_key: str | None
    transfer_group_id: str | None
    import_metadata: dict | None
    created_at: datetime
    updated_at: datetime


class PaginatedTransactionsResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int
    pages: int
