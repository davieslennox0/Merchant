# Network Manifest — Merchant Agent Mini App

Every URL, subdomain, and external resource the app can contact at runtime.

| Host | Protocol | Purpose | When contacted |
|---|---|---|---|
| `bizpal.duckdns.org` | HTTPS | App origin: static assets and the agent API (`/api/agent/chat`, proxied to a FastAPI service on the same host) | Page load; when the user sends a message in the Agent tab |
| `forno.celo-sepolia.celo-testnet.org` | HTTPS (JSON-RPC) | Celo Sepolia public RPC: cUSD `balanceOf` reads, `Transfer` event polling for payment detection, and broadcasting user-signed `transfer()` transactions | Continuously while the app is open (balance every 15s, event poll every 8s); on supplier payment |
| `celo-sepolia.blockscout.com` | HTTPS | Block explorer — outbound links only (user taps a tx hash) | Only on user tap; no fetches from app code |
| `api.wa.me` / `wa.me` | HTTPS | WhatsApp share deep link for sending a payment request | Only when the user taps "Share on WhatsApp" |
| `api.groq.com` | HTTPS | LLM completions — contacted **server-side only** by our backend, never by the client | When the backend answers an Agent-tab message |

Notes:
- No analytics, no trackers, no third-party scripts, fonts, or CDNs — the Vite
  build inlines/bundles all assets, served from the app origin.
- The wallet provider (`window.ethereum`) is injected by MiniPay; the app makes
  no other wallet-related network calls.
- No message signing (`eth_sign` / `personal_sign` / EIP-712) anywhere.
- Smart contracts: the app deploys none. It interacts only with the canonical
  Mento cUSD token on Celo Sepolia
  (`0xEF4d55D6dE8e8d73232827Cd1e9b2F2dBb45bC80`) via standard ERC-20
  `balanceOf` / `transfer` / `Transfer` events.
