import { getLedger, getStats } from "../lib/invoices";
import { CHAIN } from "../lib/wagmi";

const EXPLORER = CHAIN.blockExplorers?.default?.url || "https://celo-sepolia.blockscout.com";

export default function Ledger({ refreshKey }) {
  const stats = getStats();
  const entries = getLedger();

  return (
    <div className="screen" key={refreshKey}>
      <h2>Ledger</h2>
      <div className="stat-row">
        <div className="stat">
          <div className="stat-num in">+{stats.income.toFixed(2)}</div>
          <div className="muted small">inflows</div>
        </div>
        <div className="stat">
          <div className="stat-num out">−{stats.expenses.toFixed(2)}</div>
          <div className="muted small">outflows</div>
        </div>
        <div className="stat">
          <div className="stat-num">{stats.net.toFixed(2)}</div>
          <div className="muted small">net</div>
        </div>
      </div>

      {entries.length === 0 ? (
        <div className="empty">
          <p>Nothing here yet — paid invoices and supplier payments will show up as
          they happen.</p>
        </div>
      ) : (
        <ul className="list">
          {entries.map((e) => (
            <li key={e.id} className="list-item">
              <div className="list-main">
                <div><b>{e.label}</b></div>
                <div className="muted small">{new Date(e.at).toLocaleString()}</div>
                {e.txHash && (
                  <a className="small" href={`${EXPLORER}/tx/${e.txHash}`} target="_blank" rel="noreferrer">
                    {e.txHash.slice(0, 10)}… ↗
                  </a>
                )}
              </div>
              <div className={`amount ${e.type}`}>
                {e.type === "in" ? "+" : "−"}{e.amountCusd.toFixed(2)}
                <span className="muted small"> {e.currency}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
