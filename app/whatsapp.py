import logging

import httpx

from app.config import GRAPH_API_BASE, PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN

log = logging.getLogger(__name__)

_configured = bool(WHATSAPP_ACCESS_TOKEN and PHONE_NUMBER_ID)


def normalize_number(raw: str) -> str:
    """Meta sends 'from' as bare digits ('254712345678'); we store E.164 ('+254...')."""
    raw = raw.replace("whatsapp:", "").strip()
    if raw and not raw.startswith("+"):
        raw = "+" + raw
    return raw


def send_whatsapp(to_number: str, body: str) -> None:
    to_number = normalize_number(to_number)
    if not _configured:
        # Dev mode: no Cloud API creds — log instead of sending so local testing works.
        log.info("[DEV WHATSAPP OUT] to=%s\n%s", to_number, body)
        print(f"\n--- WhatsApp to {to_number} ---\n{body}\n---")
        return
    try:
        resp = httpx.post(
            f"{GRAPH_API_BASE}/{PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_number.lstrip("+"),
                "type": "text",
                "text": {"body": body},
            },
            timeout=30,
        )
        resp.raise_for_status()
    except Exception:
        log.exception("Failed to send WhatsApp message to %s", to_number)
