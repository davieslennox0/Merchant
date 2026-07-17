import os

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "merchant-agent-verify")
GRAPH_API_BASE = os.getenv("GRAPH_API_BASE", "https://graph.facebook.com/v21.0")

CELO_RPC_URL = os.getenv("CELO_RPC_URL", "https://alfajores-forno.celo-testnet.org")
CUSD_CONTRACT_ADDRESS = os.getenv(
    "CUSD_CONTRACT_ADDRESS", "0x874069Fa1Eb16D44d622F2e0Ca25eeA172369bC1"
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./merchant_agent.db")
CHAIN_SERVICE_URL = os.getenv("CHAIN_SERVICE_URL", "http://127.0.0.1:8002")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8001").rstrip("/")

TRANSFER_LOOKBACK_BLOCKS = int(os.getenv("TRANSFER_LOOKBACK_BLOCKS", "1000"))
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "45"))
