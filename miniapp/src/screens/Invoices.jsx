import { getInvoices } from "../lib/invoices";
import { CHAIN } from "../lib/wagmi";

const EXPLORER = CHAIN.blockExplorers?.default?.url || "https://celo-sepolia.blockscout.com";

export default function Invoices({ go, refreshKey }) {
  const invoices = getInvoices();

  if (invoices.length === 0) {
    return (
      <div className="screen">
        <h2>Invoices</h2>
        <div className="empty">
          <p>No invoices yet.</p>
          <button className="primary" onClick={() => go("new")}>Create your first invoice</button>
        </div>
      </div>
    );
  }

  return (
    <div className="screen" key={refreshKey}>
      <h2>Invoices</h2>
      <p className="muted small">
        Watching cUSD and USDC transfers to your wallet — pending invoices flip
        to paid automatically when a matching payment lands on-chain.
      </p>
      <ul className="list">
        {invoices.map((inv) => (
          <li key={inv.id} className="list-item">
            <div className="list-main">
              <div>
                <b>{inv.customerName}</b>
                {inv.description ? <span className="muted"> · {inv.description}</span> : null}
              </div>
              <div className="muted small">{new Date(inv.createdAt).toLocaleString()}</div>
              {inv.txHash && (
                <a className="small" href={`${EXPLORER}/tx/${inv.txHash}`} target="_blank" rel="noreferrer">
                  {inv.txHash.slice(0, 10)}… ↗
                </a>
              )}
            </div>
            <div className="list-side">
              <div className="amount">
                {inv.amountCusd.toFixed(2)}
                <span className="muted small"> {inv.currency || "cUSD"}</span>
              </div>
              <span className={`pill ${inv.status}`}>{inv.status}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
