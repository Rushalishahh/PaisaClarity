from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, Numeric, Date, Boolean,
    UniqueConstraint, Index
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, synonym
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # One user can have many statements. This doesn't create a database
    # column - it's a Python-side convenience so we can write
    # `some_user.statements` to get all their uploads without writing a
    # manual query. back_populates links it to Statement.user below.
    statements = relationship("Statement", back_populates="user")

    # Same pattern for investments - one user, many investments.
    investments = relationship("Investment", back_populates="user")

    # Normalized financial architecture relationships
    accounts = relationship("FinancialAccount", back_populates="user")
    custom_categories = relationship("Category", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")
    savings_goals = relationship("SavingsGoal", back_populates="user", cascade="all, delete-orphan")
    recurring_payments = relationship("RecurringPayment", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("FinancialAlert", back_populates="user", cascade="all, delete-orphan")
    ai_conversations = relationship("AIConversation", back_populates="user", cascade="all, delete-orphan")
    alert_preferences = Column(JSON, nullable=True)


class Statement(Base):
    __tablename__ = "statements"

    id = Column(Integer, primary_key=True, index=True)

    # The foreign key: this column stores the id of the row in `users`
    # that this statement belongs to. The database will enforce that this
    # value must match a real user - it can't point to a user that
    # doesn't exist.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    filename = Column(String, nullable=False)

    # The full /upload-statement response (category_totals, anomalies,
    # forecast, suggestions, subscriptions, etc.) stored as one JSON blob,
    # since we always read it back as a whole rather than querying pieces.
    result = Column(JSON, nullable=False)

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    # The other side of the relationship above - lets us write
    # `some_statement.user` to get the owning User object.
    user = relationship("User", back_populates="statements")

    # Normalized transactions extracted from this statement
    transactions = relationship("Transaction", back_populates="statement")


class Investment(Base):
    __tablename__ = "investments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String, nullable=False)

    # Discriminator column: "market" or "policy". Decides which of the
    # fields below are meaningful for this row - the rest stay NULL.
    # Enforced in application code (schemas.py), not by the database,
    # since plain Postgres columns don't have an easy built-in "only
    # allow one of these two values" constraint without extra setup.
    category = Column(String, nullable=False)

    # --- market-category fields (stocks / mutual funds) ---
    investment_type = Column(String, nullable=True)   # "mutual_fund" or "stock"
    scheme_code = Column(String, nullable=True)        # AMFI scheme code or ticker symbol
    units = Column(Numeric, nullable=True)
    purchase_date = Column(Date, nullable=True)

    # --- policy-category fields (insurance / recurring SIPs) ---
    # When the policy started. Nullable so existing rows (created before
    # this column existed) keep working; it's required only for NEW
    # policy-category rows via the InvestmentCreate schema. Needed to
    # reconstruct the premium payment history for the reality check.
    start_date = Column(Date, nullable=True)
    premium_amount = Column(Numeric, nullable=True)
    premium_frequency = Column(String, nullable=True)  # "monthly" / "quarterly" / "yearly"
    next_due_date = Column(Date, nullable=True)
    maturity_date = Column(Date, nullable=True)
    maturity_value = Column(Numeric, nullable=True)

    # --- shared field ---
    invested_amount = Column(Numeric, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="investments")


class FinancialAccount(Base):
    __tablename__ = "financial_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    account_type = Column(String(50), nullable=False, default="savings")  # savings, current, credit_card, investment, wallet, loan, imported
    currency = Column(String(3), nullable=False, default="INR")
    opening_balance = Column(Numeric(14, 2), nullable=False, default=0.00)
    account_number_mask = Column(String(20), nullable=True)  # e.g. "XX1234"
    masked_identifier = synonym("account_number_mask")
    institution_name = Column(String(100), nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False, index=True)
    is_reconciled = Column(Boolean, nullable=False, default=True)  # False for placeholder/imported accounts
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_financial_accounts_user_name"),
    )

    user = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)  # NULL = system category
    name = Column(String(100), nullable=False)
    category_type = Column(String(50), nullable=False, default="expense")  # expense, income, transfer, investment
    is_system = Column(Boolean, nullable=False, default=False, index=True)
    icon = Column(String(50), nullable=True)
    color = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_categories_user_name", "user_id", "name"),
    )

    user = relationship("User", back_populates="custom_categories")
    transactions = relationship("Transaction", back_populates="category_rel")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    statement_id = Column(Integer, ForeignKey("statements.id", ondelete="SET NULL"), nullable=True, index=True)
    source_row_index = Column(Integer, nullable=True)

    date = Column(Date, nullable=False, index=True)
    value_date = Column(Date, nullable=True)
    description = Column(String(500), nullable=False)
    merchant = Column(String(200), nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)
    type = Column(String(10), nullable=False)  # "debit" or "credit"
    classification = Column(String(20), nullable=False, default="expense")  # "expense", "income", "transfer", "investment"
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    category = Column(String(100), nullable=False, default="Other")
    ref_no = Column(String(100), nullable=True, index=True)
    balance = Column(Numeric(14, 2), nullable=True)
    transaction_key = Column(String(255), nullable=False, index=True)
    transfer_group_id = Column(String(36), nullable=True, index=True)
    import_metadata = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("statement_id", "source_row_index", name="uq_statement_source_row"),
        Index("ix_transactions_user_date", "user_id", "date"),
        Index("ix_transactions_user_account", "user_id", "account_id"),
        Index("ix_transactions_user_category", "user_id", "category_id"),
        Index("ix_transactions_user_key", "user_id", "transaction_key"),
    )

    user = relationship("User", back_populates="transactions")
    account = relationship("FinancialAccount", back_populates="transactions")
    statement = relationship("Statement", back_populates="transactions")
    category_rel = relationship("Category", back_populates="transactions")


# ---------------------------------------------------------------------------
# Phase 7: Budget Management and Savings Goals
# ---------------------------------------------------------------------------

class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    month = Column(Integer, nullable=False)  # 1-12
    year = Column(Integer, nullable=False)   # e.g. 2026
    total_budget_limit = Column(Numeric(14, 2), nullable=True)  # Optional overall monthly limit
    warning_threshold = Column(Numeric(5, 2), nullable=False, default=80.00)  # e.g. 80.0%
    is_archived = Column(Boolean, nullable=False, default=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "month", "year", name="uq_budget_user_month_year"),
        Index("ix_budgets_user_period", "user_id", "year", "month"),
    )

    user = relationship("User", back_populates="budgets")
    allocations = relationship("BudgetAllocation", back_populates="budget", cascade="all, delete-orphan")


class BudgetAllocation(Base):
    __tablename__ = "budget_allocations"

    id = Column(Integer, primary_key=True, index=True)
    budget_id = Column(Integer, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    category_name = Column(String(100), nullable=False)  # Denormalized category name
    allocated_amount = Column(Numeric(14, 2), nullable=False, default=0.00)
    notes = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("budget_id", "category_name", name="uq_budget_allocation_category"),
    )

    budget = relationship("Budget", back_populates="allocations")
    category = relationship("Category")


class SavingsGoal(Base):
    __tablename__ = "savings_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    target_amount = Column(Numeric(14, 2), nullable=False)
    target_date = Column(Date, nullable=True)  # Optional target deadline
    category = Column(String(50), nullable=True)  # Emergency, Travel, Vehicle, Gadget, etc.
    notes = Column(Text, nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_savings_goals_user", "user_id", "is_archived"),
    )

    user = relationship("User", back_populates="savings_goals")
    contributions = relationship("SavingsContribution", back_populates="goal", cascade="all, delete-orphan")


class SavingsContribution(Base):
    __tablename__ = "savings_contributions"

    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("savings_goals.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    contribution_date = Column(Date, nullable=False)
    contribution_type = Column(String(20), nullable=False, default="deposit")  # deposit or withdrawal
    notes = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_savings_contributions_goal_date", "goal_id", "contribution_date"),
    )

    goal = relationship("SavingsGoal", back_populates="contributions")
    user = relationship("User")


# ---------------------------------------------------------------------------
# Phase 8: Cash Flow Intelligence, Recurring Payments, and Financial Alerts
# ---------------------------------------------------------------------------

class RecurringPayment(Base):
    __tablename__ = "recurring_payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    category = Column(String(100), nullable=False, default="Bills")
    average_amount = Column(Numeric(14, 2), nullable=False)
    frequency = Column(String(50), nullable=False, default="monthly")  # monthly, weekly, quarterly, yearly
    status = Column(String(20), nullable=False, default="detected")   # detected, confirmed, rejected, inactive
    next_expected_date = Column(Date, nullable=True)
    last_payment_date = Column(Date, nullable=True)
    first_seen_date = Column(Date, nullable=True)
    occurrence_count = Column(Integer, nullable=False, default=1)
    is_auto_detected = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_recurring_user_status", "user_id", "status"),
        Index("ix_recurring_user_next_date", "user_id", "next_expected_date"),
    )

    user = relationship("User", back_populates="recurring_payments")
    account = relationship("FinancialAccount")


class FinancialAlert(Base):
    __tablename__ = "financial_alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False)  # budget_warning, budget_exceeded, unusual_spending, expense_surge, upcoming_recurring, savings_goal_behind
    severity = Column(String(20), nullable=False, default="info")  # info, warning, critical
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    related_entity_type = Column(String(50), nullable=True)  # budget, goal, transaction, recurring, account
    related_entity_id = Column(Integer, nullable=True)
    dedup_key = Column(String(255), nullable=False, index=True)

    is_read = Column(Boolean, nullable=False, default=False)
    is_dismissed = Column(Boolean, nullable=False, default=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "dedup_key", name="uq_alert_user_dedup"),
        Index("ix_alerts_user_unread", "user_id", "is_dismissed", "is_read"),
    )

    user = relationship("User", back_populates="alerts")


# ---------------------------------------------------------------------------
# Phase 9: AI Financial Copilot Models
# ---------------------------------------------------------------------------

class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="New Conversation")
    is_archived = Column(Boolean, nullable=False, default=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="ai_conversations")
    messages = relationship("AIMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="AIMessage.id.asc()")


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system, tool
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    tool_results = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship("AIConversation", back_populates="messages")
    user = relationship("User")
