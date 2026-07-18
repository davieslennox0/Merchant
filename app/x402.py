"""x402 payment gate for the paid agent endpoint.

Implements the resource-server side of the x402 "exact" scheme on Celo
mainnet: challenge with 402 + payment requirements, then verify and settle
the client's signed EIP-3009 authorization through the Celo facilitator
(which relays the transfer on-chain, gasless for both parties).
"""

import base64
import json
import logging
import os

import httpx

log = logging.getLogger("merchant-agent.x402")

FACILITATOR_URL = os.getenv("X402_FACILITATOR_URL", "https://api.x402.celo.org").rstrip("/")
PAYTO = os.getenv("X402_PAYTO", "")
API_KEY = os.getenv("X402_API_KEY", "")
USDC_MAINNET = os.getenv("USDC_MAINNET", "0xcebA9300f2b948710d2653dD7B07f33A8B32118C")
PRICE_ATOMIC = os.getenv("X402_PRICE_ATOMIC", "1000")  # USDC has 6 decimals
RESOURCE_URL = os.getenv("PUBLIC_BASE_URL", "https://bizpal.duckdns.org").rstrip("/") + "/api/agent/paid-chat"

X402_VERSION = 1


def payment_requirements() -> dict:
    return {
        "scheme": "exact",
        "network": "celo",
        "maxAmountRequired": PRICE_ATOMIC,
        "resource": RESOURCE_URL,
        "description": "Merchant Agent paid chat — per-request USDC micropayment",
        "mimeType": "application/json",
        "payTo": PAYTO,
        "maxTimeoutSeconds": 120,
        "asset": USDC_MAINNET,
        "extra": {"name": "USDC", "version": "2"},
    }


def challenge_body(error: str = "X-PAYMENT header is required") -> dict:
    return {"x402Version": X402_VERSION, "error": error, "accepts": [payment_requirements()]}


def decode_payment_header(header: str) -> dict:
    return json.loads(base64.b64decode(header))


async def verify_and_settle(payment_payload: dict) -> dict:
    """Verify then settle through the facilitator. Returns the settle response
    on success; raises X402Error with a client-safe message otherwise."""
    body = {
        "x402Version": X402_VERSION,
        "paymentPayload": payment_payload,
        "paymentRequirements": payment_requirements(),
    }
    async with httpx.AsyncClient(timeout=90) as client:
        vr = await client.post(f"{FACILITATOR_URL}/verify", json=body)
        verify = vr.json() if vr.headers.get("content-type", "").startswith("application/json") else {}
        if vr.status_code != 200 or not verify.get("isValid"):
            reason = verify.get("invalidReason") or verify.get("error") or f"verify HTTP {vr.status_code}"
            raise X402Error(f"payment verification failed: {reason}")
        sr = await client.post(f"{FACILITATOR_URL}/settle", json=body, headers={"X-API-Key": API_KEY})
        settle = sr.json() if sr.headers.get("content-type", "").startswith("application/json") else {}
        if sr.status_code != 200 or not (settle.get("success") or settle.get("transaction")):
            reason = settle.get("errorReason") or settle.get("error") or f"settle HTTP {sr.status_code}"
            raise X402Error(f"payment settlement failed: {reason}")
    log.info("x402 settled: tx=%s payer=%s", settle.get("transaction"), settle.get("payer"))
    return settle


def settlement_header(settle: dict) -> str:
    return base64.b64encode(json.dumps(settle).encode()).decode()


class X402Error(Exception):
    pass
