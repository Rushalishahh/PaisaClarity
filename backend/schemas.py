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


# ---------------------------------------------------------------------------
# Phase 7: Budget & Savings Goal Schemas
# ---------------------------------------------------------------------------

class BudgetAllocationCreate(BaseModel):
    category_id: int | None = None
    category_name: str
    allocated_amount: Decimal
    notes: str | None = None

    @field_validator("category_name")
    @classmethod
    def validate_category_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Category name cannot be empty")
        return s

    @field_validator("allocated_amount")
    @classmethod
    def validate_allocated_amount(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("Allocated amount cannot be negative")
        return v.quantize(Decimal("0.01"))


class BudgetCreate(BaseModel):
    month: int
    year: int
    total_budget_limit: Decimal | None = None
    warning_threshold: Decimal = Decimal("80.00")
    allocations: list[BudgetAllocationCreate] = []

    @field_validator("month")
    @classmethod
    def validate_month(cls, v: int) -> int:
        if v < 1 or v > 12:
            raise ValueError("Month must be between 1 and 12")
        return v

    @field_validator("year")
    @classmethod
    def validate_year(cls, v: int) -> int:
        if v < 2000 or v > 2100:
            raise ValueError("Year must be between 2000 and 2100")
        return v

    @field_validator("total_budget_limit")
    @classmethod
    def validate_limit(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            if v < Decimal("0.00"):
                raise ValueError("Budget limit cannot be negative")
            return v.quantize(Decimal("0.01"))
        return v

    @field_validator("warning_threshold")
    @classmethod
    def validate_warning_threshold(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00") or v > Decimal("100.00"):
            raise ValueError("Warning threshold must be between 0 and 100")
        return v.quantize(Decimal("0.01"))


class BudgetUpdate(BaseModel):
    total_budget_limit: Decimal | None = None
    warning_threshold: Decimal | None = None
    is_archived: bool | None = None
    allocations: list[BudgetAllocationCreate] | None = None

    @field_validator("total_budget_limit")
    @classmethod
    def validate_limit(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            if v < Decimal("0.00"):
                raise ValueError("Budget limit cannot be negative")
            return v.quantize(Decimal("0.01"))
        return v

    @field_validator("warning_threshold")
    @classmethod
    def validate_threshold(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            if v < Decimal("0.00") or v > Decimal("100.00"):
                raise ValueError("Warning threshold must be between 0 and 100")
            return v.quantize(Decimal("0.01"))
        return v


class BudgetAllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    budget_id: int
    category_id: int | None
    category_name: str
    allocated_amount: Decimal
    actual_spent: Decimal = Decimal("0.00")
    remaining: Decimal = Decimal("0.00")
    utilization_pct: float = 0.0
    is_exceeded: bool = False
    is_warning: bool = False
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    month: int
    year: int
    total_budget_limit: Decimal | None
    total_allocated: Decimal
    total_spent: Decimal
    total_remaining: Decimal
    overall_utilization_pct: float
    overall_is_exceeded: bool
    warning_threshold: Decimal
    is_archived: bool
    allocations: list[BudgetAllocationResponse]
    created_at: datetime
    updated_at: datetime


class BudgetPerformanceMonth(BaseModel):
    month: int
    year: int
    total_budget_limit: Decimal | None
    total_allocated: Decimal
    total_spent: Decimal
    overall_utilization_pct: float
    is_exceeded: bool


class BudgetPerformanceResponse(BaseModel):
    history: list[BudgetPerformanceMonth]


class SavingsContributionCreate(BaseModel):
    amount: Decimal
    contribution_date: dt.date
    contribution_type: str = "deposit"  # "deposit" | "withdrawal"
    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("Contribution amount must be greater than zero")
        return v.quantize(Decimal("0.01"))

    @field_validator("contribution_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        s = v.strip().lower()
        if s not in ("deposit", "withdrawal"):
            raise ValueError("Contribution type must be 'deposit' or 'withdrawal'")
        return s


class SavingsContributionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goal_id: int
    user_id: int
    amount: Decimal
    contribution_date: dt.date
    contribution_type: str
    notes: str | None
    created_at: datetime


class SavingsGoalCreate(BaseModel):
    name: str
    target_amount: Decimal
    target_date: dt.date | None = None
    category: str | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Goal name cannot be empty")
        return s

    @field_validator("target_amount")
    @classmethod
    def validate_target_amount(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("Target amount must be greater than zero")
        return v.quantize(Decimal("0.01"))


class SavingsGoalUpdate(BaseModel):
    name: str | None = None
    target_amount: Decimal | None = None
    target_date: dt.date | None = None
    category: str | None = None
    notes: str | None = None
    is_archived: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Goal name cannot be empty")
            return s
        return v

    @field_validator("target_amount")
    @classmethod
    def validate_target_amount(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            if v <= Decimal("0.00"):
                raise ValueError("Target amount must be greater than zero")
            return v.quantize(Decimal("0.01"))
        return v


class SavingsGoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    target_amount: Decimal
    target_date: dt.date | None
    category: str | None
    notes: str | None
    is_archived: bool
    total_saved: Decimal
    remaining_target: Decimal
    completion_pct: float
    is_completed: bool
    monthly_savings_needed: Decimal | None
    contributions: list[SavingsContributionResponse] = []
    created_at: datetime
    updated_at: datetime
