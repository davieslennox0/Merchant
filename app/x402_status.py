"""Aggregated live status for the x402 payment loop: local payment log,
facilitator credit balance, on-chain USDC balances, and the Track 2 Dune
leaderboard (cached hard — the Dune free tier rate-limits quickly)."""

import json
import os
import time
from pathlib import Path

import httpx

LOG_FILE = Path(__file__).parent.parent / "logs" / "x402-payments.ndjson"
MERCHANT = os.getenv("X402_PAYTO", "0x53Aa8c3Ed977F5540B070703785726e5fcAdC461")
PAYER = os.getenv("X402_PAYER_ADDRESS", "0xf21799F4d1716fFCe280a8d4F41F2345170c5ded")
USDC = os.getenv("USDC_MAINNET", "0xcebA9300f2b948710d2653dD7B07f33A8B32118C")
DUNE_API_KEY = os.getenv("DUNE_API_KEY", "")
TRACK2_QUERY = "7868467"
RPC = "https://forno.celo.org"

_cache: dict = {}


def _cached(key: str, ttl: float):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    return None


def _store(key: str, value):
    _cache[key] = (time.monotonic(), value)
    return value


def read_log() -> dict:
    payments, sweeps, recent = 0, 0, []
    if LOG_FILE.exists():
        with LOG_FILE.open() as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("kind") == "sweep":
                    sweeps += 1
                else:
                    payments += 1
                recent.append(row)
    return {"payments": payments, "sweeps": sweeps, "recent": recent[-12:][::-1]}


async def _balance_of(client: httpx.AsyncClient, holder: str) -> float:
    data = "0x70a08231" + holder.lower().replace("0x", "").rjust(64, "0")
    r = await client.post(RPC, json={
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": USDC, "data": data}, "latest"],
    })
    return int(r.json().get("result", "0x0"), 16) / 1e6


async def chain_and_credits() -> dict:
    if (hit := _cached("chain", 30)) is not None:
        return hit
    out = {"payer_usdc": None, "merchant_usdc": None, "credits": None}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            out["payer_usdc"] = await _balance_of(client, PAYER)
            out["merchant_usdc"] = await _balance_of(client, MERCHANT)
        except Exception:
            pass
        try:
            r = await client.get(f"https://x402.celo.org/api/account?address={MERCHANT}")
            out["credits"] = r.json().get("balances", {}).get("mainnet")
        except Exception:
            pass
    return _store("chain", out)


async def leaderboard() -> list:
    if (hit := _cached("dune", 1800)) is not None:
        return hit
    if not DUNE_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"https://api.dune.com/api/v1/query/{TRACK2_QUERY}/results",
                params={"limit": 12},
                headers={"X-Dune-API-Key": DUNE_API_KEY},
            )
            rows = r.json().get("result", {}).get("rows", [])
        board = [
            {
                "team": row.get("team") or row.get("participant") or "?",
                "repo": row.get("github_repo"),
                "payments": row.get("x402_payments", 0),
                "volume": round(row.get("x402_volume_usd") or 0, 2),
            }
            for row in rows
        ]
        return _store("dune", board)
    except Exception:
        return _cache.get("dune", (0, []))[1]


async def status() -> dict:
    log = read_log()
    chain = await chain_and_credits()
    board = await leaderboard()
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "merchant": MERCHANT,
        "payer": PAYER,
        **log,
        **chain,
        "leaderboard": board,
    }
