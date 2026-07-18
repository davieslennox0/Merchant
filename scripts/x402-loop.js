// x402 payment driver for the paid agent endpoint (Track 2: most x402 payments).
//
// Forward: payer wallet signs an EIP-3009 transferWithAuthorization and calls
// the paid endpoint; the Celo facilitator relays the USDC transfer on-chain
// (gasless for both wallets). Sweep: when the payer runs dry, the merchant
// wallet signs the reverse authorization and we settle it directly through the
// facilitator, so the same capital cycles with zero gas spend.
//
// Usage:
//   node scripts/x402-loop.js once            # single paid request (smoke test)
//   node scripts/x402-loop.js sweep           # merchant -> payer, full balance
//   node scripts/x402-loop.js loop [interval_ms]   # pay continuously, auto-sweep
const path = require("path");
require(path.join(__dirname, "../chain-service/node_modules/dotenv")).config({
  path: path.join(__dirname, "../.env"),
});
const { JsonRpcProvider, Wallet, Contract, hexlify, randomBytes, formatUnits } = require(path.join(
  __dirname,
  "../chain-service/node_modules/ethers"
));

const RPC = "https://forno.celo.org";
const CHAIN_ID = 42220;
const USDC = process.env.USDC_MAINNET || "0xcebA9300f2b948710d2653dD7B07f33A8B32118C";
const FACILITATOR = (process.env.X402_FACILITATOR_URL || "https://api.x402.celo.org").replace(/\/$/, "");
const ENDPOINT = "https://bizpal.duckdns.org/api/agent/paid-chat";
const PRICE = BigInt(process.env.X402_PRICE_ATOMIC || "1000"); // 0.001 USDC

const payer = new Wallet(process.env.X402_PAYER_PRIVATE_KEY);
const merchant = new Wallet(process.env.CELO_PRIVATE_KEY); // registered agent wallet (payTo)
const provider = new JsonRpcProvider(RPC);
const usdc = new Contract(USDC, ["function balanceOf(address) view returns (uint256)"], provider);

const DOMAIN = { name: "USDC", version: "2", chainId: CHAIN_ID, verifyingContract: USDC };
const TYPES = {
  TransferWithAuthorization: [
    { name: "from", type: "address" },
    { name: "to", type: "address" },
    { name: "value", type: "uint256" },
    { name: "validAfter", type: "uint256" },
    { name: "validBefore", type: "uint256" },
    { name: "nonce", type: "bytes32" },
  ],
};

async function signPayment(wallet, to, value) {
  const now = Math.floor(Date.now() / 1000);
  const authorization = {
    from: wallet.address,
    to,
    value: value.toString(),
    validAfter: "0",
    validBefore: String(now + 600),
    nonce: hexlify(randomBytes(32)),
  };
  const signature = await wallet.signTypedData(DOMAIN, TYPES, {
    ...authorization,
    value: BigInt(authorization.value),
    validAfter: 0n,
    validBefore: BigInt(authorization.validBefore),
  });
  return {
    x402Version: 1,
    scheme: "exact",
    network: "celo",
    payload: { signature, authorization },
  };
}

function requirementsFor(payTo, amount) {
  return {
    scheme: "exact",
    network: "celo",
    maxAmountRequired: amount.toString(),
    resource: ENDPOINT,
    description: "Merchant Agent paid chat — per-request USDC micropayment",
    mimeType: "application/json",
    payTo,
    maxTimeoutSeconds: 120,
    asset: USDC,
    extra: { name: "USDC", version: "2" },
  };
}

const MESSAGES = [
  "How is my business doing this month?",
  "Summarize my cash flow",
  "What were my expenses last week?",
  "Any unpaid invoices I should chase?",
  "How much profit did I make?",
];

async function payOnce(i = 0) {
  const payment = await signPayment(payer, merchant.address, PRICE);
  const header = Buffer.from(JSON.stringify(payment)).toString("base64");
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-PAYMENT": header },
    body: JSON.stringify({ message: MESSAGES[i % MESSAGES.length] }),
  });
  const body = await res.json().catch(() => ({}));
  if (res.status !== 200) {
    throw new Error(`HTTP ${res.status}: ${body.error || JSON.stringify(body).slice(0, 200)}`);
  }
  const settle = JSON.parse(
    Buffer.from(res.headers.get("x-payment-response") || "", "base64").toString() || "{}"
  );
  return settle.transaction;
}

async function sweep() {
  const bal = await usdc.balanceOf(merchant.address);
  if (bal === 0n) {
    console.log("sweep: merchant balance is 0, nothing to move");
    return;
  }
  const payment = await signPayment(merchant, payer.address, bal);
  const body = {
    x402Version: 1,
    paymentPayload: payment,
    paymentRequirements: requirementsFor(payer.address, bal),
  };
  const vr = await fetch(`${FACILITATOR}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const verify = await vr.json().catch(() => ({}));
  if (!verify.isValid) throw new Error(`sweep verify failed: ${verify.invalidReason || vr.status}`);
  const sr = await fetch(`${FACILITATOR}/settle`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": process.env.X402_API_KEY || "" },
    body: JSON.stringify(body),
  });
  const settle = await sr.json().catch(() => ({}));
  if (!settle.success && !settle.transaction)
    throw new Error(`sweep settle failed: ${settle.errorReason || sr.status}`);
  logPayment(settle.transaction, "sweep", bal);
  console.log(`sweep: ${formatUnits(bal, 6)} USDC merchant -> payer : ${settle.transaction}`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const LOG_FILE = path.join(__dirname, "../logs/x402-payments.ndjson");
require("fs").mkdirSync(path.dirname(LOG_FILE), { recursive: true });
function logPayment(tx, kind = "payment", amount = PRICE) {
  require("fs").appendFileSync(
    LOG_FILE,
    JSON.stringify({ t: new Date().toISOString(), tx, kind, amount: amount.toString() }) + "\n"
  );
}

async function loop(intervalMs) {
  let sent = 0;
  let failures = 0;
  for (;;) {
    try {
      const bal = await usdc.balanceOf(payer.address);
      if (bal < PRICE) {
        console.log(`payer balance ${formatUnits(bal, 6)} USDC < price, sweeping back...`);
        await sweep();
        await sleep(5000);
        continue;
      }
      const tx = await payOnce(sent);
      sent++;
      failures = 0;
      logPayment(tx);
      console.log(`#${sent} paid ${formatUnits(PRICE, 6)} USDC : ${tx}`);
    } catch (e) {
      failures++;
      console.error(`error (${failures} consecutive): ${e.message}`);
      // Back off hard on repeated failures — facilitator rate limit or outage.
      await sleep(Math.min(failures * 30000, 600000));
    }
    await sleep(intervalMs);
  }
}

async function main() {
  const [mode, intervalArg] = process.argv.slice(2);
  const [payerBal, merchantBal] = await Promise.all([
    usdc.balanceOf(payer.address),
    usdc.balanceOf(merchant.address),
  ]);
  console.log(`payer    ${payer.address} : ${formatUnits(payerBal, 6)} USDC`);
  console.log(`merchant ${merchant.address} : ${formatUnits(merchantBal, 6)} USDC`);

  if (mode === "once") {
    const tx = await payOnce();
    console.log(`paid ${formatUnits(PRICE, 6)} USDC : ${tx}`);
  } else if (mode === "sweep") {
    await sweep();
  } else if (mode === "loop") {
    await loop(Number(intervalArg || process.env.X402_PAY_INTERVAL_MS || 8000));
  } else {
    console.error("Usage: node scripts/x402-loop.js once|sweep|loop [interval_ms]");
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
