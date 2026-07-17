# Merchant Agent 🛍️ — MiniPay Mini App

An AI-agent "neobank layer" for small merchants, built for the **Celo Agentic
Payments & DeFAI Hackathon**. Runs natively inside **MiniPay** on **Celo Sepolia**.

- **Invoices** — create them in two taps or by telling the agent
  ("invoice John 50 for delivery"); share the payment request via WhatsApp link.
- **Real payment detection** — the app watches cUSD `Transfer` events to your
  wallet and auto-marks a matching invoice paid (with tx-hash dedup + backfill
  of recent blocks on open).
- **Pay suppliers** — cUSD ERC-20 `transfer()` signed in MiniPay; you approve,
  the agent never holds funds.
- **Ledger** — inflows − outflows with explorer links.
- **In-app agent** — Groq-powered chat that turns natural language into
  prefilled on-chain actions and plain-language profit summaries.

## Architecture

```
MiniPay (webview) ──► https://bizpal.duckdns.org
                        ├── static Vite/React build (miniapp/dist, via Caddy)
                        │     wagmi + viem → Celo Sepolia forno RPC
                        │     • cUSD balance, transfers, Transfer-event watcher
                        │     • invoices/ledger in localStorage (no backend DB)
                        └── /api/agent/chat ──► FastAPI (port 8010) ──► Groq
                              intent classification + grounded replies only —
                              all transactions are signed client-side in MiniPay
```

**Key addresses (Celo Sepolia, chain id 11142220)**
- cUSD (Mento Dollar): `0xEF4d55D6dE8e8d73232827Cd1e9b2F2dBb45bC80` (18 decimals, verified on-chain)
- RPC: `https://forno.celo-sepolia.celo-testnet.org` (free, no key)
- Explorer: https://celo-sepolia.blockscout.com
- Faucet: https://faucet.celo.org/celo-sepolia

> ⚠️ Alfajores is sunset — its RPC no longer resolves. Do not use it.

## Develop

```bash
cd miniapp
npm install
npx vite build          # outputs dist/, served by Caddy
npx vite                # dev server (proxies /api → 127.0.0.1:8010)
```

Backend (agent API only):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# .env needs GROQ_API_KEY
pm2 start ecosystem.config.js
```

## Test inside MiniPay

1. In MiniPay: tap the **compass** icon → scroll to **Test Page** (enable
   Developer Mode in settings if hidden).
2. Enter `https://bizpal.duckdns.org` — the deployed build; no tunnel needed.
   (For the local dev server, expose it with ngrok/localtunnel and use that URL.)
3. The wallet auto-connects (no connect button, per MiniPay guidelines).

**MiniPay constraints honored**: cUSD fee currency, legacy (type-0)
transactions only, no message signing anywhere in the app.

## Demo script

1. Dashboard shows live cUSD balance on Celo Sepolia.
2. Agent tab: *"invoice John 50 cUSD for delivery"* → agent parses it → tap
   **Create this invoice** → share the payment request via WhatsApp.
3. Send 50 cUSD to the merchant wallet from another wallet (faucet-funded).
4. Within ~8s the invoice flips to **paid** with a toast + explorer link — no
   manual marking.
5. Agent tab: *"how am I doing this month?"* → plain-language profit summary
   from real ledger numbers.
6. Pay supplier: *"pay Maria 20 cUSD"* → prefilled form → sign in MiniPay →
   outflow appears in the ledger.

## Scope cuts (deliberate)

Testnet only · localStorage ledger (single device) · cUSD only · no KYC/lending/
FX/push · agent API is unauthenticated (demo).

## Legacy

`app/`, `chain-service/`, `templates/` are the earlier WhatsApp-channel build
(Twilio → Meta Cloud API), pivoted away from after WhatsApp Business
verification blockers. The FastAPI app still serves the webhook endpoints, but
only `/api/agent/chat` is used by the Mini App.
