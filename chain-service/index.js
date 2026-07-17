// Celo Alfajores chain service: cUSD balance, incoming-transfer scan, and sends.
// The FastAPI backend talks to this over localhost HTTP.
require("dotenv").config({ path: require("path").join(__dirname, "..", ".env") });
const express = require("express");
const { ethers } = require("ethers");

const RPC_URL = process.env.CELO_RPC_URL || "https://alfajores-forno.celo-testnet.org";
const CUSD_ADDRESS = process.env.CUSD_CONTRACT_ADDRESS || "0x874069Fa1Eb16D44d622F2e0Ca25eeA172369bC1";
const PRIVATE_KEY = process.env.CELO_PRIVATE_KEY;
const PORT = parseInt(process.env.CHAIN_SERVICE_PORT || "8002", 10);
const DEFAULT_LOOKBACK = parseInt(process.env.TRANSFER_LOOKBACK_BLOCKS || "1000", 10);

const ERC20_ABI = [
  "function balanceOf(address) view returns (uint256)",
  "function transfer(address to, uint256 value) returns (bool)",
  "event Transfer(address indexed from, address indexed to, uint256 value)",
];

const provider = new ethers.JsonRpcProvider(RPC_URL);
const wallet = PRIVATE_KEY ? new ethers.Wallet(PRIVATE_KEY, provider) : null;
const cusd = new ethers.Contract(CUSD_ADDRESS, ERC20_ABI, wallet || provider);

const app = express();
app.use(express.json());

app.get("/health", (_req, res) => res.json({ ok: true }));

app.get("/wallet", (_req, res) => {
  if (!wallet) return res.status(500).json({ error: "CELO_PRIVATE_KEY not configured" });
  res.json({ address: wallet.address });
});

app.get("/balance/:address", async (req, res) => {
  try {
    const raw = await cusd.balanceOf(ethers.getAddress(req.params.address));
    res.json({ address: req.params.address, balanceCusd: ethers.formatUnits(raw, 18) });
  } catch (err) {
    res.status(500).json({ error: String(err.message || err) });
  }
});

// Recent cUSD Transfer events into ?to=, scanning the last ?lookback= blocks.
app.get("/transfers", async (req, res) => {
  try {
    const to = ethers.getAddress(req.query.to);
    const lookback = Math.min(parseInt(req.query.lookback || DEFAULT_LOOKBACK, 10), 10000);
    const latest = await provider.getBlockNumber();
    const fromBlock = Math.max(latest - lookback, 0);
    const events = await cusd.queryFilter(cusd.filters.Transfer(null, to), fromBlock, latest);
    const transfers = events.map((ev) => ({
      txHash: ev.transactionHash,
      from: ev.args.from,
      to: ev.args.to,
      amountCusd: ethers.formatUnits(ev.args.value, 18),
      blockNumber: ev.blockNumber,
    }));
    // newest first so amount-matching prefers the latest payment
    transfers.sort((a, b) => b.blockNumber - a.blockNumber);
    res.json({ to, fromBlock, latest, transfers });
  } catch (err) {
    res.status(500).json({ error: String(err.message || err) });
  }
});

// Send cUSD from the service wallet; waits for 1 confirmation.
app.post("/send", async (req, res) => {
  try {
    if (!wallet) return res.status(500).json({ error: "CELO_PRIVATE_KEY not configured" });
    const to = ethers.getAddress(req.body.to);
    const amount = ethers.parseUnits(String(req.body.amountCusd), 18);
    const tx = await cusd.transfer(to, amount);
    const receipt = await tx.wait(1);
    if (receipt.status !== 1) return res.status(500).json({ error: "transaction reverted", txHash: tx.hash });
    res.json({ txHash: tx.hash, blockNumber: receipt.blockNumber });
  } catch (err) {
    res.status(500).json({ error: String(err.shortMessage || err.message || err) });
  }
});

app.listen(PORT, "127.0.0.1", () => {
  console.log(`chain-service listening on 127.0.0.1:${PORT} (rpc=${RPC_URL})`);
  if (wallet) console.log(`service wallet: ${wallet.address}`);
  else console.warn("CELO_PRIVATE_KEY not set — /wallet and /send disabled");
});
