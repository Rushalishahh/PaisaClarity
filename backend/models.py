from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Numeric, Date
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