"""Thin HTTP client for the Node.js chain-service (ethers.js on Celo Alfajores)."""

import logging

import httpx

from app.config import CHAIN_SERVICE_URL, TRANSFER_LOOKBACK_BLOCKS

log = logging.getLogger(__name__)

_READ_TIMEOUT = 30.0
_SEND_TIMEOUT = 120.0  # waits for on-chain confirmation


class ChainServiceError(Exception):
    pass


def _get(path: str, params: dict | None = None) -> dict:
    last_err: Exception | None = None
    for attempt in range(2):  # single retry, per scope
        try:
            r = httpx.get(f"{CHAIN_SERVICE_URL}{path}", params=params, timeout=_READ_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("chain-service GET %s failed (attempt %d): %s", path, attempt + 1, e)
    raise ChainServiceError(f"chain-service unreachable: {last_err}")


def get_service_wallet() -> str:
    """Address of the wallet backing CELO_PRIVATE_KEY (used as default merchant wallet)."""
    return _get("/wallet")["address"]


def get_cusd_balance(address: str) -> float:
    return float(_get(f"/balance/{address}")["balanceCusd"])


def get_incoming_transfers(to_address: str, lookback: int | None = None) -> list[dict]:
    """Recent cUSD Transfer events into `to_address`.

    Returns [{"txHash", "from", "to", "amountCusd", "blockNumber"}, ...]
    """
    data = _get(
        "/transfers",
        params={"to": to_address, "lookback": lookback or TRANSFER_LOOKBACK_BLOCKS},
    )
    return data["transfers"]


def send_cusd(to_address: str, amount_cusd: float) -> str:
    """Send cUSD from the service wallet. Returns the tx hash."""
    try:
        r = httpx.post(
            f"{CHAIN_SERVICE_URL}/send",
            json={"to": to_address, "amountCusd": str(amount_cusd)},
            timeout=_SEND_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()["txHash"]
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:300]
        raise ChainServiceError(f"transfer failed: {detail}") from e
    except Exception as e:  # noqa: BLE001
        raise ChainServiceError(f"transfer failed: {e}") from e
