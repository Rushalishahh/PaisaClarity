from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, JSON, Numeric, Date, Boolean,
    UniqueConstraint, Index
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
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