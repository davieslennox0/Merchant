import { erc20Abi, formatUnits } from "viem";
import { useReadContract } from "wagmi";
import { TOKENS } from "../lib/wagmi";
import { getStats } from "../lib/invoices";

const [CUSD, USDC] = TOKENS;

function useTokenBalance(token, address) {
  const { data, isLoading } = useReadContract({
    address: token.address,
    abi: erc20Abi,
    functionName: "balanceOf",
    args: [address],
    query: { enabled: !!address, refetchInterval: 15000 },
  });
  return isLoading || data === undefined
    ? "…"
    : Number(formatUnits(data, token.decimals)).toFixed(2);
}

export default function Dashboard({ address, isMiniPay, go }) {
  const stats = getStats();
  const cusdBalance = useTokenBalance(CUSD, address);
  const usdcBalance = useTokenBalance(USDC, address);

  return (
    <div className="screen">
      <div className="balance-card">
        <div className="muted">wallet balance</div>
        <div className="balance">
          {cusdBalance}
          <span className="unit"> cUSD</span>
        </div>
        <div className="muted">
          {usdcBalance}
          <span className="unit small"> USDC</span>
        </div>
        <div className="muted small">
          {address ? `${address.slice(0, 6)}…${address.slice(-4)}` : "no wallet"} · Celo
          Sepolia
        </div>
      </div>

      <div className="stat-row">
        <div className="stat">
          <div className="stat-num">{stats.owed.toFixed(2)}</div>
          <div className="muted small">owed to you</div>
        </div>
        <div className="stat">
          <div className="stat-num">{stats.income.toFixed(2)}</div>
          <div className="muted small">collected</div>
        </div>
        <div className="stat">
          <div className="stat-num">{stats.net.toFixed(2)}</div>
          <div className="muted small">net</div>
        </div>
      </div>

      <div className="actions">
        <button className="primary" onClick={() => go("new")}>
          + New invoice
        </button>
        <button onClick={() => go("pay")}>Pay supplier</button>
        <button onClick={() => go("agent")}>🤖 Ask the agent</button>
      </div>

      {!isMiniPay && (
        <p className="muted small hint">
          Tip: open this app inside MiniPay (compass icon → Test Page) for the full
          experience — your wallet connects automatically, no login needed.
        </p>
      )}

      <p className="muted small footer-links">
        <a href="/terms.html">Terms</a> · <a href="/privacy.html">Privacy</a> ·{" "}
        <a href="/support.html">Support</a>
      </p>
    </div>
  );
}
