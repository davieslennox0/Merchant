from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True)
    whatsapp_number = Column(String, unique=True, nullable=False, index=True)
    business_name = Column(String, nullable=False, default="My Business")
    wallet_address = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    customer_name = Column(String, nullable=False)
    customer_whatsapp = Column(String, nullable=True, index=True)
    amount_cusd = Column(Float, nullable=False)
    description = Column(String, default="")
    # pending | paid | overdue | disputed
    status = Column(String, default="pending", index=True)
    payment_address = Column(String, nullable=False)
    tx_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    due_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    last_reminder_sent_at = Column(DateTime, nullable=True)

    OPEN_STATUSES = ("pending", "overdue", "disputed")


class SupplierPayment(Base):
    __tablename__ = "supplier_payments"

    id = Column(Integer, primary_key=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    supplier_name = Column(String, nullable=False)
    supplier_address = Column(String, nullable=False)
    amount_cusd = Column(Float, nullable=False)
    # pending | sent | failed
    status = Column(String, default="pending")
    tx_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    # invoice_paid | supplier_payment
    entry_type = Column(String, nullable=False)
    amount_cusd = Column(Float, nullable=False)
    ref_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(engine)


@contextmanager
def get_session():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
