"""Groq LLM integration: intent classification (per role) and free-form replies."""

import json
import logging
import re

from groq import Groq

from app.config import GROQ_API_KEY, GROQ_MODEL

log = logging.getLogger(__name__)

_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

OWNER_CLASSIFY_SYSTEM = """You classify WhatsApp messages from a small-business OWNER \
talking to their business assistant. Reply with ONLY a JSON object, no prose.

Intents and fields:
- create_invoice: {"customer_name": str, "customer_whatsapp": str|null (E.164 like +254712345678 if present), "amount_cusd": number, "description": str}
- pay_supplier: {"supplier_name": str, "supplier_address": str|null (0x... if present), "amount_cusd": number}
- check_profit: {"period": "this_month"|"last_month"|"all_time"}
- general_query: {}

Output shape: {"intent": "<name>", "fields": {...}}
Amounts like "$50", "50 dollars", "50 cUSD" all mean amount_cusd=50.
If the message doesn't clearly match the first three intents, use general_query."""

CUSTOMER_CLASSIFY_SYSTEM = """You classify WhatsApp messages from a CUSTOMER who has \
received an invoice from a small business. Reply with ONLY a JSON object, no prose.

Intents:
- confirm_payment_intent: customer says they already paid / just sent the money
- ask_invoice_status: asking whether payment was received, or what they owe
- ask_how_to_pay: asking how/where to pay, wants the link or instructions again
- dispute_invoice: says the amount/charge is wrong, refuses to pay, disputes it. Fields: {"reason": str}
- general_query: anything else

Output shape: {"intent": "<name>", "fields": {...}}"""


def _chat(system: str, user: str, max_tokens: int = 400, json_mode: bool = False) -> str:
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=max_tokens,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        **kwargs,
    )
    return resp.choices[0].message.content or ""


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON in LLM output: {text[:200]}")
    return json.loads(match.group(0))


def classify(role: str, message: str) -> dict:
    """Returns {"intent": str, "fields": dict}. Falls back to general_query on any error."""
    system = OWNER_CLASSIFY_SYSTEM if role == "owner" else CUSTOMER_CLASSIFY_SYSTEM
    if _client is None:
        log.warning("No GROQ_API_KEY set; defaulting to general_query")
        return {"intent": "general_query", "fields": {}}
    try:
        result = _extract_json(_chat(system, message, json_mode=True))
        result.setdefault("fields", {})
        return result
    except Exception:
        log.exception("Intent classification failed")
        return {"intent": "general_query", "fields": {}}


def generate_reply(role: str, message: str, context: str) -> str:
    """Free-form WhatsApp reply for general queries, grounded in provided context."""
    if _client is None:
        return "Sorry, I couldn't process that right now. Please try again shortly."
    persona = (
        "You are Merchant Agent, a WhatsApp assistant for a small business owner. "
        "You help them invoice customers, pay suppliers in cUSD on Celo, and track profit."
        if role == "owner"
        else "You are Merchant Agent, a polite WhatsApp assistant replying to a customer "
        "of a small business about their invoice and how to pay it in cUSD on Celo (e.g. via MiniPay)."
    )
    system = (
        f"{persona}\nKeep replies short and WhatsApp-friendly (2-4 sentences, "
        "no markdown headers). Never invent payment amounts, statuses, or tx hashes — "
        "only use facts from the context below.\n\nContext:\n" + context
    )
    try:
        return _chat(system, message, max_tokens=300).strip()
    except Exception:
        log.exception("Reply generation failed")
        return "Sorry, I couldn't process that right now. Please try again shortly."


def summarize_profit(business_name: str, period_label: str, stats: dict) -> str:
    """Plain-language profit summary for the owner."""
    fallback = (
        f"{period_label}: {stats['invoices_paid']} invoice(s) paid totaling "
        f"{stats['income']:.2f} cUSD, {stats['supplier_payments']} supplier payment(s) totaling "
        f"{stats['expenses']:.2f} cUSD. Net: {stats['net']:.2f} cUSD."
    )
    if _client is None:
        return fallback
    try:
        return _chat(
            "Write a short, encouraging WhatsApp message (2-4 sentences, plain text) "
            "summarizing business performance for the owner. Use the exact numbers given; "
            "do not invent any.",
            f"Business: {business_name}\nPeriod: {period_label}\n" + json.dumps(stats),
            max_tokens=300,
        ).strip()
    except Exception:
        log.exception("Profit summary generation failed")
        return fallback


def looks_like_owner_activity(message: str) -> bool:
    """For unknown senders: does this read like merchant activity (invoice/supplier/profit)?"""
    result = classify("owner", message)
    return result["intent"] in ("create_invoice", "pay_supplier", "check_profit")
