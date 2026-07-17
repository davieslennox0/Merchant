// Sends cUSD from the burner "customer" wallet (CELO_PRIVATE_KEY in ../.env)
// to the merchant's MiniPay wallet, so pending invoices auto-settle in the app.
// Usage: node scripts/pay-invoice.js <merchant_address> <amount_cusd> [count]
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

async function main() {
  const [to, amountArg, countArg] = process.argv.slice(2);
  if (!to || !amountArg) {
    console.error("Usage: node scripts/pay-invoice.js <merchant_address> <amount_cusd> [count]");
    process.exit(1);
  }
  const count = Number(countArg || 1);
  const provider = new JsonRpcProvider(process.env.CELO_RPC_URL);
  const wallet = new Wallet(process.env.CELO_PRIVATE_KEY, provider);
  const cusd = new Contract(process.env.CUSD_CONTRACT_ADDRESS, ERC20, wallet);

  const [celo, cusdBal] = await Promise.all([
    provider.getBalance(wallet.address),
    cusd.balanceOf(wallet.address),
  ]);
  console.log(`payer ${wallet.address}`);
  console.log(`  CELO ${formatUnits(celo, 18)} | cUSD ${formatUnits(cusdBal, 18)}`);

  for (let i = 0; i < count; i++) {
    const tx = await cusd.transfer(to, parseUnits(amountArg, 18));
    console.log(`sent ${amountArg} cUSD -> ${to} : ${tx.hash}`);
    const receipt = await tx.wait(1);
    console.log(`  confirmed in block ${receipt.blockNumber}`);
  }
}

main().catch((e) => {
  console.error(e.shortMessage || e.message);
  process.exit(1);
});
