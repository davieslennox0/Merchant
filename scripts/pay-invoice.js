// Sends cUSD or USDC from the burner "customer" wallet (CELO_PRIVATE_KEY in
// ../.env) to the merchant's MiniPay wallet, so pending invoices auto-settle
// in the app.
// Usage: node scripts/pay-invoice.js <merchant_address> <amount> [count] [cusd|usdc]
const path = require("path");
require(path.join(__dirname, "../chain-service/node_modules/dotenv")).config({
  path: path.join(__dirname, "../.env"),
});
const { JsonRpcProvider, Wallet, Contract, parseUnits, formatUnits } = require(path.join(
  __dirname,
  "../chain-service/node_modules/ethers"
));

const ERC20 = [
  "function transfer(address to, uint256 value) returns (bool)",
  "function balanceOf(address) view returns (uint256)",
];

// ERC-8021 attribution suffix for the Celo hackathon leaderboard
// (toDataSuffix("celo_64d533d628d1") from @celo/attribution-tags).
const ATTRIBUTION_SUFFIX =
  "63656c6f5f363464353333643632386431110080218021802180218021802180218021";

const TOKENS = {
  cusd: { symbol: "cUSD", address: process.env.CUSD_CONTRACT_ADDRESS, decimals: 18 },
  // Circle USDC on Celo Sepolia (what faucet.celo.org dispenses)
  usdc: { symbol: "USDC", address: "0x01C5C0122039549AD1493B8220cABEdD739BC44E", decimals: 6 },
};

async function main() {
  const [to, amountArg, countArg, tokenArg] = process.argv.slice(2);
  const token = TOKENS[(tokenArg || "cusd").toLowerCase()];
  if (!to || !amountArg || !token) {
    console.error("Usage: node scripts/pay-invoice.js <merchant_address> <amount> [count] [cusd|usdc]");
    process.exit(1);
  }
  const count = Number(countArg || 1);
  const provider = new JsonRpcProvider(process.env.CELO_RPC_URL);
  const wallet = new Wallet(process.env.CELO_PRIVATE_KEY, provider);
  const erc20 = new Contract(token.address, ERC20, wallet);

  const [celo, bal] = await Promise.all([
    provider.getBalance(wallet.address),
    erc20.balanceOf(wallet.address),
  ]);
  console.log(`payer ${wallet.address}`);
  console.log(`  CELO ${formatUnits(celo, 18)} | ${token.symbol} ${formatUnits(bal, token.decimals)}`);

  for (let i = 0; i < count; i++) {
    const data =
      erc20.interface.encodeFunctionData("transfer", [to, parseUnits(amountArg, token.decimals)]) +
      ATTRIBUTION_SUFFIX;
    const tx = await wallet.sendTransaction({ to: erc20.target, data });
    console.log(`sent ${amountArg} ${token.symbol} -> ${to} : ${tx.hash}`);
    const receipt = await tx.wait(1);
    console.log(`  confirmed in block ${receipt.blockNumber}`);
  }
}

main().catch((e) => {
  console.error(e.shortMessage || e.message);
  process.exit(1);
});
