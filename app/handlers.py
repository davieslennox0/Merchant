"""Inbound message routing (owner vs. customer) and intent handlers for both roles."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import chain, llm, payments
from app.config import PUBLIC_BASE_URL
from app.db import Invoice, LedgerEntry, Merchant, SupplierPayment
from app.whatsapp import send_whatsapp

log = logging.getLogger(__name__)

INVOICE_DUE_DAYS = 3
# "Recent activity" window used to break owner/customer ambiguity.
RECENT_ACTIVITY_HOURS = 48


def payment_link(invoice: Invoice) -> str:
    return f"{PUBLIC_BASE_URL}/pay/{invoice.id}"


def _open_invoices_for(db: Session, number: str) -> list[Invoice]:
    return (
        db.execute(
            select(Invoice)
            .where(
                Invoice.customer_whatsapp == number,
                Invoice.status.in_(Invoice.OPEN_STATUSES),
            )
            .order_by(Invoice.created_at.desc())
        )
        .scalars()
        .all()
    )


def _resolve_role(db: Session, number: str) -> tuple[str, Merchant | None, list[Invoice]]:
    """Returns (role, merchant_or_none, open_invoices). role: owner|customer|unknown."""
    merchant = db.execute(
        select(Merchant).where(Merchant.whatsapp_number == number)
    ).scalar_one_or_none()
    open_invoices = _open_invoices_for(db, number)

    if merchant and open_invoices:
        # Both roles match: treat as customer only if there's an open invoice with
        # recent activity; otherwise default to merchant.
        cutoff = datetime.utcnow() - timedelta(hours=RECENT_ACTIVITY_HOURS)
        recent = any(
            (inv.created_at and inv.created_at >= cutoff)
            or (inv.last_reminder_sent_at and inv.last_reminder_sent_at >= cutoff)
            for inv in open_invoices
        )
        return ("customer", merchant, open_invoices) if recent else ("owner", merchant, open_invoices)
    if merchant:
        return "owner", merchant, []
    # Any invoice history at all (incl. paid) makes them a known customer.
    any_invoice = db.execute(
        select(Invoice.id).where(Invoice.customer_whatsapp == number)
    ).first()
    if open_invoices or any_invoice:
        return "customer", None, open_invoices
    return "unknown", None, []


def handle_inbound(db: Session, from_number: str, body: str) -> None:
    if not body:
        return
    role, merchant, open_invoices = _resolve_role(db, from_number)
    log.info("Inbound from %s resolved as %s: %r", from_number, role, body[:120])

    if role == "owner":
        _handle_owner(db, merchant, body)
    elif role == "customer":
        _handle_customer(db, from_number, body, open_invoices)
    else:
        _handle_unknown(db, from_number, body)


# ---------------------------------------------------------------- unknown

def _handle_unknown(db: Session, number: str, body: str) -> None:
    result = llm.classify("owner", body)
    if result["intent"] in ("create_invoice", "pay_supplier", "check_profit"):
        # Reads like merchant activity → auto-register, then handle the message.
        try:
            wallet = chain.get_service_wallet()
        except chain.ChainServiceError:
            send_whatsapp(
                number,
                "Welcome! I couldn't set up your wallet right now — please try again "
                "in a minute.",
            )
            return
        merchant = Merchant(
            whatsapp_number=number, business_name="My Business", wallet_address=wallet
        )
        db.add(merchant)
        db.flush()
        send_whatsapp(
            number,
            "👋 Welcome to Merchant Agent! I've set you up as a new business. "
            "You can invoice customers, pay suppliers, and track profit — all in cUSD "
            "on Celo. Now handling your request…",
        )
        _dispatch_owner(db, merchant, body, result)
    else:
        send_whatsapp(
            number,
            "Hi! I don't see an invoice linked to this number. If a business sent you "
            "a payment link, please check that message and pay through the link. "
            "If you're a business owner, try something like: "
            '"invoice John $50 for delivery".',
        )


# ---------------------------------------------------------------- owner side

def _handle_owner(db: Session, merchant: Merchant, body: str) -> None:
    result = llm.classify("owner", body)
    _dispatch_owner(db, merchant, body, result)


def _dispatch_owner(db: Session, merchant: Merchant, body: str, result: dict) -> None:
    intent, fields = result["intent"], result.get("fields", {})
    if intent == "create_invoice":
        _owner_create_invoice(db, merchant, fields)
    elif intent == "pay_supplier":
        _owner_pay_supplier(db, merchant, fields)
    elif intent == "check_profit":
        _owner_check_profit(db, merchant, fields)
    else:
        _owner_general_query(db, merchant, body)


def _owner_create_invoice(db: Session, merchant: Merchant, fields: dict) -> None:
    amount = fields.get("amount_cusd")
    customer_name = (fields.get("customer_name") or "").strip()
    if not amount or not customer_name:
        send_whatsapp(
            merchant.whatsapp_number,
            'I need a customer name and amount. Try: "invoice John $50 for delivery" '
            "(add their WhatsApp number and I'll send them the payment link directly).",
        )
        return
    invoice = Invoice(
        merchant_id=merchant.id,
        customer_name=customer_name,
        customer_whatsapp=(fields.get("customer_whatsapp") or None),
        amount_cusd=float(amount),
        description=fields.get("description") or "",
        status="pending",
        payment_address=merchant.wallet_address,
        due_at=datetime.utcnow() + timedelta(days=INVOICE_DUE_DAYS),
    )
    db.add(invoice)
    db.flush()

    link = payment_link(invoice)
    desc = f" for {invoice.description}" if invoice.description else ""
    if invoice.customer_whatsapp:
        send_whatsapp(
            invoice.customer_whatsapp,
            f"Hi {customer_name}! {merchant.business_name} sent you an invoice"
            f"{desc}: {invoice.amount_cusd:.2f} cUSD.\n\nPay here: {link}\n\n"
            "Open the link on your phone to scan the QR with MiniPay, or send cUSD "
            "manually to the address shown. Reply here if you have any questions.",
        )
        delivered = f" and sent the payment link to {customer_name}"
    else:
        delivered = f" — share this link with {customer_name}: {link}"
    send_whatsapp(
        merchant.whatsapp_number,
        f"✅ Invoice #{invoice.id} created: {invoice.amount_cusd:.2f} cUSD "
        f"for {customer_name}{desc}{delivered}. I'll watch the chain and confirm "
        "as soon as they pay.",
    )


def _owner_pay_supplier(db: Session, merchant: Merchant, fields: dict) -> None:
    amount = fields.get("amount_cusd")
    supplier_name = (fields.get("supplier_name") or "supplier").strip()
    supplier_address = (fields.get("supplier_address") or "").strip()
    if not amount:
        send_whatsapp(
            merchant.whatsapp_number,
            'How much should I send? Try: "pay Maria 20 cUSD to 0x…".',
        )
        return
    if not supplier_address.startswith("0x") or len(supplier_address) != 42:
        send_whatsapp(
            merchant.whatsapp_number,
            f"I need {supplier_name}'s Celo wallet address to send the payment. "
            f'Resend like: "pay {supplier_name} {amount} cUSD to 0x…".',
        )
        return

    amount = float(amount)
    try:
        balance = chain.get_cusd_balance(merchant.wallet_address)
    except chain.ChainServiceError:
        send_whatsapp(
            merchant.whatsapp_number,
            "I couldn't reach the Celo network to check your balance. Nothing was "
            "sent — please try again in a minute.",
        )
        return
    if balance < amount:
        send_whatsapp(
            merchant.whatsapp_number,
            f"⚠️ Not enough funds: you have {balance:.2f} cUSD but this payment needs "
            f"{amount:.2f} cUSD (short {amount - balance:.2f}). I didn't send anything.",
        )
        return

    sp = SupplierPayment(
        merchant_id=merchant.id,
        supplier_name=supplier_name,
        supplier_address=supplier_address,
        amount_cusd=amount,
        status="pending",
    )
    db.add(sp)
    db.flush()
    try:
        tx_hash = chain.send_cusd(supplier_address, amount)
    except chain.ChainServiceError as e:
        sp.status = "failed"
        log.warning("Supplier payment %s failed: %s", sp.id, e)
        send_whatsapp(
            merchant.whatsapp_number,
            f"❌ The {amount:.2f} cUSD payment to {supplier_name} failed to send. "
            "Your balance was not charged for a confirmed transfer — please try again.",
        )
        return
    sp.status = "sent"
    sp.tx_hash = tx_hash
    sp.sent_at = datetime.utcnow()
    db.add(
        LedgerEntry(
            merchant_id=merchant.id,
            entry_type="supplier_payment",
            amount_cusd=amount,
            ref_id=sp.id,
        )
    )
    send_whatsapp(
        merchant.whatsapp_number,
        f"✅ Sent {amount:.2f} cUSD to {supplier_name} "
        f"({supplier_address[:8]}…) on Celo. Tx: {tx_hash[:10]}… "
        "Recorded in your ledger.",
    )


def _month_bounds(period: str) -> tuple[datetime | None, datetime | None, str]:
    now = datetime.utcnow()
    if period == "last_month":
        first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end = first_this
        last_month_start = (first_this - timedelta(days=1)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return last_month_start, last_month_end, "last month"
    if period == "all_time":
        return None, None, "all time"
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, None, "this month"


def profit_stats(db: Session, merchant_id: int, period: str = "this_month") -> tuple[dict, str]:
    start, end, label = _month_bounds(period)
    q = select(LedgerEntry).where(LedgerEntry.merchant_id == merchant_id)
    if start:
        q = q.where(LedgerEntry.created_at >= start)
    if end:
        q = q.where(LedgerEntry.created_at < end)
    entries = db.execute(q).scalars().all()
    income = sum(e.amount_cusd for e in entries if e.entry_type == "invoice_paid")
    expenses = sum(e.amount_cusd for e in entries if e.entry_type == "supplier_payment")
    stats = {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net": round(income - expenses, 2),
        "invoices_paid": sum(1 for e in entries if e.entry_type == "invoice_paid"),
        "supplier_payments": sum(1 for e in entries if e.entry_type == "supplier_payment"),
    }
    return stats, label


def _owner_check_profit(db: Session, merchant: Merchant, fields: dict) -> None:
    stats, label = profit_stats(db, merchant.id, fields.get("period") or "this_month")
    send_whatsapp(
        merchant.whatsapp_number,
        llm.summarize_profit(merchant.business_name, label, stats),
    )


def _owner_general_query(db: Session, merchant: Merchant, body: str) -> None:
    stats, label = profit_stats(db, merchant.id)
    open_count = len(
        db.execute(
            select(Invoice).where(
                Invoice.merchant_id == merchant.id,
                Invoice.status.in_(Invoice.OPEN_STATUSES),
            )
        )
        .scalars()
        .all()
    )
    context = (
        f"Business: {merchant.business_name}. Wallet: {merchant.wallet_address}.\n"
        f"{label}: income {stats['income']} cUSD, expenses {stats['expenses']} cUSD, "
        f"net {stats['net']} cUSD. Open (unpaid) invoices: {open_count}.\n"
        'The owner can say things like "invoice John $50 for delivery", '
        '"pay Maria 20 cUSD to 0x…", or "how am I doing this month?".'
    )
    send_whatsapp(merchant.whatsapp_number, llm.generate_reply("owner", body, context))


# ---------------------------------------------------------------- customer side

def _handle_customer(
    db: Session, number: str, body: str, open_invoices: list[Invoice]
) -> None:
    result = llm.classify("customer", body)
    intent, fields = result["intent"], result.get("fields", {})
    invoice = open_invoices[0] if open_invoices else None

    if intent == "confirm_payment_intent":
        _customer_confirm_payment(db, number, invoice)
    elif intent == "ask_invoice_status":
        _customer_status(db, number, invoice)
    elif intent == "ask_how_to_pay":
        _customer_how_to_pay(db, number, invoice)
    elif intent == "dispute_invoice":
        _customer_dispute(db, number, body, invoice, fields.get("reason") or body)
    else:
        _customer_general_query(db, number, body, invoice)


def _no_open_invoice_reply(db: Session, number: str) -> None:
    last_paid = db.execute(
        select(Invoice)
        .where(Invoice.customer_whatsapp == number, Invoice.status == "paid")
        .order_by(Invoice.paid_at.desc())
    ).scalars().first()
    if last_paid:
        merchant = db.get(Merchant, last_paid.merchant_id)
        send_whatsapp(
            number,
            f"You're all settled up! Your last invoice from {merchant.business_name} "
            f"({last_paid.amount_cusd:.2f} cUSD) was paid and verified on-chain. 🎉",
        )
    else:
        send_whatsapp(number, "I don't see any open invoice for this number right now.")


def _customer_confirm_payment(db: Session, number: str, invoice: Invoice | None) -> None:
    if invoice is None:
        _no_open_invoice_reply(db, number)
        return
    merchant = db.get(Merchant, invoice.merchant_id)
    send_whatsapp(number, "Let me verify that on the Celo network — one moment… 🔍")
    try:
        settled = payments.check_invoice_now(db, invoice)
    except chain.ChainServiceError:
        send_whatsapp(
            number,
            "I couldn't reach the network to verify just now. I'll keep checking "
            "automatically and confirm as soon as your payment lands.",
        )
        return
    if not settled:
        # settle path already messages both parties when it succeeds
        send_whatsapp(
            number,
            f"I checked the chain but don't see your {invoice.amount_cusd:.2f} cUSD "
            f"payment to {merchant.business_name} yet. Transfers usually confirm in "
            "seconds — if you just sent it, give it a moment and I'll confirm "
            f"automatically. Need the payment details again? {payment_link(invoice)}",
        )


def _customer_status(db: Session, number: str, invoice: Invoice | None) -> None:
    if invoice is None:
        _no_open_invoice_reply(db, number)
        return
    merchant = db.get(Merchant, invoice.merchant_id)
    desc = f" for {invoice.description}" if invoice.description else ""
    due = f" (due {invoice.due_at.strftime('%b %d')})" if invoice.due_at else ""
    status_word = {
        "pending": "still unpaid",
        "overdue": "overdue",
        "disputed": "under review after your dispute",
    }.get(invoice.status, invoice.status)
    send_whatsapp(
        number,
        f"Your invoice from {merchant.business_name}{desc} is {status_word}: "
        f"{invoice.amount_cusd:.2f} cUSD{due}. Pay here: {payment_link(invoice)}",
    )


def _customer_how_to_pay(db: Session, number: str, invoice: Invoice | None) -> None:
    if invoice is None:
        _no_open_invoice_reply(db, number)
        return
    merchant = db.get(Merchant, invoice.merchant_id)
    send_whatsapp(
        number,
        f"Here's how to pay {merchant.business_name} ({invoice.amount_cusd:.2f} cUSD):\n\n"
        f"1️⃣ Open {payment_link(invoice)}\n"
        "2️⃣ Scan the QR code with MiniPay (or any Celo wallet)\n"
        f"3️⃣ Or send {invoice.amount_cusd:.2f} cUSD manually to:\n"
        f"{invoice.payment_address}\n\n"
        'When you\'ve sent it, reply "I paid" and I\'ll verify it on-chain right away.',
    )


def _customer_dispute(
    db: Session, number: str, body: str, invoice: Invoice | None, reason: str
) -> None:
    if invoice is None:
        _no_open_invoice_reply(db, number)
        return
    invoice.status = "disputed"
    merchant = db.get(Merchant, invoice.merchant_id)
    send_whatsapp(
        number,
        f"Got it — I've flagged invoice #{invoice.id} "
        f"({invoice.amount_cusd:.2f} cUSD) as disputed and told "
        f"{merchant.business_name}. They'll review it and get back to you; "
        "you don't need to pay while it's under review.",
    )
    send_whatsapp(
        merchant.whatsapp_number,
        f"⚠️ Dispute on invoice #{invoice.id} ({invoice.customer_name}, "
        f"{invoice.amount_cusd:.2f} cUSD). Their message:\n\n\"{body}\"\n\n"
        "I won't change or cancel the invoice — please resolve it with them directly "
        "(e.g. send a corrected invoice).",
    )


def _customer_general_query(
    db: Session, number: str, body: str, invoice: Invoice | None
) -> None:
    if invoice is None:
        context = "This customer has no open invoice."
    else:
        merchant = db.get(Merchant, invoice.merchant_id)
        context = (
            f"Open invoice from {merchant.business_name}: {invoice.amount_cusd:.2f} cUSD "
            f"for '{invoice.description}', status {invoice.status}. "
            f"Payment link: {payment_link(invoice)}. "
            f"They can pay by scanning the QR on that page with MiniPay or sending cUSD "
            f"to {invoice.payment_address}."
        )
    send_whatsapp(number, llm.generate_reply("customer", body, context))


# ---------------------------------------------------------------- reminders

def run_reminders(db: Session) -> int:
    """Nudge customers on invoices pending >24h with no reminder sent yet.
    Also flips pending invoices past due date to overdue."""
    now = datetime.utcnow()
    stale = (
        db.execute(
            select(Invoice).where(
                Invoice.status.in_(("pending", "overdue")),
                Invoice.created_at <= now - timedelta(hours=24),
                Invoice.last_reminder_sent_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    sent = 0
    for invoice in stale:
        if invoice.due_at and invoice.due_at < now and invoice.status == "pending":
            invoice.status = "overdue"
        if not invoice.customer_whatsapp:
            continue
        merchant = db.get(Merchant, invoice.merchant_id)
        desc = f" for {invoice.description}" if invoice.description else ""
        send_whatsapp(
            invoice.customer_whatsapp,
            f"👋 Friendly reminder from {merchant.business_name}: your invoice"
            f"{desc} of {invoice.amount_cusd:.2f} cUSD is still open. "
            f"Pay in seconds here: {payment_link(invoice)} — "
            'reply "how do I pay?" if you need help.',
        )
        invoice.last_reminder_sent_at = now
        sent += 1
    return sent
