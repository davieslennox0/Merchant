import base64
import json
import logging
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import qrcode
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select

from app import llm, x402
from app.config import CUSD_CONTRACT_ADDRESS, WHATSAPP_VERIFY_TOKEN
from app.db import Invoice, LedgerEntry, Merchant, get_session, init_db
from app.handlers import handle_inbound, run_reminders
from app.whatsapp import normalize_number

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("merchant-agent")

app = FastAPI(title="Merchant Agent")
init_db()

_templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)

@app.get("/webhook/whatsapp")
def whatsapp_webhook_verify(request: Request):
    """Meta webhook verification handshake: echo hub.challenge if the token matches."""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN
    ):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(403, "Verification token mismatch")


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """Single entry point for all WhatsApp traffic (owner and customer sides).
    Parses Meta Cloud API webhook JSON; replies go out via the Graph API."""
    try:
        payload = await request.json()
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                # Delivery/read status callbacks arrive on the same webhook — ignore them.
                for message in value.get("messages", []):
                    if message.get("type") != "text":
                        continue
                    number = normalize_number(message.get("from", ""))
                    body = message.get("text", {}).get("body", "").strip()
                    if not number or not body:
                        continue
                    with get_session() as db:
                        handle_inbound(db, number, body)
    except Exception:
        log.exception("Webhook handling failed")
    return {"status": "ok"}


def _eip681_uri(invoice: Invoice) -> str:
    """EIP-681 payment request: cUSD transfer on Alfajores (chain id 44787)."""
    wei = int(Decimal(str(invoice.amount_cusd)) * Decimal(10**18))
    return (
        f"ethereum:{CUSD_CONTRACT_ADDRESS}@44787/transfer"
        f"?address={invoice.payment_address}&uint256={wei}"
    )


def _qr_data_uri(content: str) -> str:
    img = qrcode.make(content, box_size=8, border=2)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@app.get("/pay/{invoice_id}", response_class=HTMLResponse)
def pay_page(invoice_id: int):
    with get_session() as db:
        invoice = db.get(Invoice, invoice_id)
        if invoice is None:
            raise HTTPException(404, "Invoice not found")
        merchant = db.get(Merchant, invoice.merchant_id)
        uri = _eip681_uri(invoice)
        html = _templates.get_template("pay.html").render(
            invoice=invoice,
            merchant=merchant,
            payment_uri=uri,
            qr_data_uri=_qr_data_uri(uri),
        )
    return HTMLResponse(html)


@app.post("/admin/run-reminders")
def admin_run_reminders():
    with get_session() as db:
        sent = run_reminders(db)
    return {"reminders_sent": sent}


@app.get("/admin/merchant/{merchant_id}/ledger")
def merchant_ledger(merchant_id: int):
    with get_session() as db:
        merchant = db.get(Merchant, merchant_id)
        if merchant is None:
            raise HTTPException(404, "Merchant not found")
        entries = (
            db.execute(
                select(LedgerEntry)
                .where(LedgerEntry.merchant_id == merchant_id)
                .order_by(LedgerEntry.created_at.desc())
            )
            .scalars()
            .all()
        )
        return {
            "merchant": {
                "id": merchant.id,
                "business_name": merchant.business_name,
                "wallet_address": merchant.wallet_address,
            },
            "entries": [
                {
                    "id": e.id,
                    "type": e.entry_type,
                    "amount_cusd": e.amount_cusd,
                    "ref_id": e.ref_id,
                    "created_at": e.created_at.isoformat(),
                }
                for e in entries
            ],
        }


PERIOD_LABELS = {
    "this_month": "This month",
    "last_month": "Last month",
    "all_time": "All time",
}


def _agent_reply(payload: dict) -> dict:
    message = (payload.get("message") or "").strip()
    ctx = payload.get("context") or {}
    stats = ctx.get("stats") or {}
    business = ctx.get("businessName") or "your business"

    result = llm.classify("owner", message)
    intent, fields = result["intent"], result.get("fields", {})

    if intent == "create_invoice":
        amount = fields.get("amount_cusd")
        name = fields.get("customer_name") or "the customer"
        reply = (
            f"Got it — invoice {name} for {amount} cUSD"
            + (f" ({fields['description']})" if fields.get("description") else "")
            + ". Tap below to create it; I'll watch the chain and mark it paid automatically."
        )
    elif intent == "pay_supplier":
        amount = fields.get("amount_cusd")
        name = fields.get("supplier_name") or "the supplier"
        reply = (
            f"Ready to send {amount} cUSD to {name}. Tap below to review — "
            "you approve the transfer in your wallet, I never touch your funds."
        )
    elif intent == "check_profit":
        period = fields.get("period", "all_time")
        stats.setdefault("invoices_paid", 0)
        stats.setdefault("income", 0)
        stats.setdefault("supplier_payments", 0)
        stats.setdefault("expenses", 0)
        stats.setdefault("net", stats.get("income", 0) - stats.get("expenses", 0))
        reply = llm.summarize_profit(business, PERIOD_LABELS.get(period, period), stats)
    else:
        reply = llm.generate_reply(
            "owner",
            message,
            "Business: " + business + "\nCurrent stats (cUSD): " + json.dumps(stats)
            + "\nThe app runs inside MiniPay on Celo Sepolia testnet; invoices are "
            "auto-marked paid when a matching cUSD transfer arrives on-chain.",
        )

    return {"intent": intent, "fields": fields, "reply": reply}


@app.post("/api/agent/chat")
async def agent_chat(request: Request):
    """Groq-backed agent for the MiniPay Mini App. The frontend sends the
    merchant's local stats as context; on-chain actions are executed client-side
    by the wallet owner, so this endpoint only classifies and replies."""
    return _agent_reply(await request.json())


@app.post("/api/agent/paid-chat")
async def agent_paid_chat(request: Request):
    """x402-gated agent chat for external agents/clients: each request costs a
    USDC micropayment on Celo mainnet, settled via the Celo x402 facilitator."""
    header = request.headers.get("X-PAYMENT")
    if not header:
        return JSONResponse(x402.challenge_body(), status_code=402)
    try:
        payment = x402.decode_payment_header(header)
    except Exception:
        return JSONResponse(x402.challenge_body("malformed X-PAYMENT header"), status_code=402)
    try:
        settle = await x402.verify_and_settle(payment)
    except x402.X402Error as e:
        return JSONResponse(x402.challenge_body(str(e)), status_code=402)
    result = _agent_reply(await request.json())
    return JSONResponse(result, headers={"X-PAYMENT-RESPONSE": x402.settlement_header(settle)})


@app.get("/health")
def health():
    return {"ok": True}
