"""On-chain payment verification shared by the background poller and the
customer's "I paid" fast path."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import chain
from app.db import Invoice, LedgerEntry, Merchant
from app.whatsapp import send_whatsapp

log = logging.getLogger(__name__)

AMOUNT_TOLERANCE_CUSD = 0.005


def _find_matching_transfer(db: Session, invoice: Invoice) -> dict | None:
    transfers = chain.get_incoming_transfers(invoice.payment_address)
    for t in transfers:
        if abs(float(t["amountCusd"]) - invoice.amount_cusd) > AMOUNT_TOLERANCE_CUSD:
            continue
        # A tx hash can settle only one invoice.
        already_used = db.execute(
            select(Invoice.id).where(Invoice.tx_hash == t["txHash"])
        ).first()
        if already_used:
            continue
        return t
    return None


def settle_invoice(db: Session, invoice: Invoice, transfer: dict) -> None:
    invoice.status = "paid"
    invoice.paid_at = datetime.utcnow()
    invoice.tx_hash = transfer["txHash"]
    db.add(
        LedgerEntry(
            merchant_id=invoice.merchant_id,
            entry_type="invoice_paid",
            amount_cusd=invoice.amount_cusd,
            ref_id=invoice.id,
        )
    )
    db.flush()

    merchant = db.get(Merchant, invoice.merchant_id)
    tx_short = transfer["txHash"][:10] + "…"
    if invoice.customer_whatsapp:
        send_whatsapp(
            invoice.customer_whatsapp,
            f"✅ Payment received! Your {invoice.amount_cusd:.2f} cUSD payment to "
            f"{merchant.business_name} is confirmed on Celo (tx {tx_short}). "
            f"Thank you, {invoice.customer_name}!",
        )
    send_whatsapp(
        merchant.whatsapp_number,
        f"💰 {invoice.customer_name} paid invoice #{invoice.id} — "
        f"{invoice.amount_cusd:.2f} cUSD verified on-chain (tx {tx_short}). "
        f"It's been added to your ledger.",
    )
    log.info("Invoice %s settled via tx %s", invoice.id, transfer["txHash"])


def check_invoice_now(db: Session, invoice: Invoice) -> bool:
    """Immediate on-chain check for one invoice. Returns True if it got settled."""
    if invoice.status == "paid":
        return True
    transfer = _find_matching_transfer(db, invoice)
    if transfer is None:
        return False
    settle_invoice(db, invoice, transfer)
    return True


def poll_open_invoices(db: Session) -> int:
    """One poll pass over all open invoices. Returns number settled."""
    open_invoices = (
        db.execute(select(Invoice).where(Invoice.status.in_(("pending", "overdue"))))
        .scalars()
        .all()
    )
    settled = 0
    for invoice in open_invoices:
        try:
            if check_invoice_now(db, invoice):
                settled += 1
                db.commit()
        except chain.ChainServiceError as e:
            log.warning("Skipping invoice %s this cycle: %s", invoice.id, e)
    return settled
