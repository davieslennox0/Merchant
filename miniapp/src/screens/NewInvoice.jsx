import { useState } from "react";
import { createInvoice } from "../lib/invoices";
import { TOKENS } from "../lib/wagmi";

export default function NewInvoice({ address, go, prefill }) {
  const [customerName, setCustomerName] = useState(prefill?.customer_name || "");
  const [amount, setAmount] = useState(prefill?.amount_cusd?.toString() || "");
  const [currency, setCurrency] = useState(prefill?.currency || "cUSD");
  const [description, setDescription] = useState(prefill?.description || "");
  const [created, setCreated] = useState(null);
  const [error, setError] = useState("");

  const submit = (e) => {
    e.preventDefault();
    const amt = Number(amount);
    if (!customerName.trim()) return setError("Customer name is required.");
    if (!amt || amt <= 0) return setError("Enter a positive amount.");
    setError("");
    setCreated(createInvoice({ customerName: customerName.trim(), amountCusd: amt, description, currency }));
  };

  if (created) {
    const shareText = encodeURIComponent(
      `Hi ${created.customerName}! Please pay ${created.amountCusd.toFixed(2)} ${created.currency}` +
        (created.description ? ` for ${created.description}` : "") +
        ` on Celo (MiniPay) to:\n${address}\n\nI'll get notified automatically when it lands.`
    );
    return (
      <div className="screen">
        <div className="card success">
          <h3>Invoice created ✓</h3>
          <p>
            <b>{created.customerName}</b> owes{" "}
            <b>{created.amountCusd.toFixed(2)} {created.currency}</b>
            {created.description ? <> for {created.description}</> : null}.
          </p>
          <p className="muted small">
            When they send exactly this amount to your wallet, the invoice is marked
            paid automatically.
          </p>
        </div>
        <div className="actions">
          <a className="btn primary" href={`https://wa.me/?text=${shareText}`} target="_blank" rel="noreferrer">
            Share on WhatsApp
          </a>
          <button onClick={() => navigator.clipboard?.writeText(decodeURIComponent(shareText))}>
            Copy payment request
          </button>
          <button onClick={() => go("invoices")}>View invoices</button>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <h2>New invoice</h2>
      <form onSubmit={submit} className="form">
        <label>
          Customer name
          <input value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="John" />
        </label>
        <label>
          Amount
          <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" placeholder="50" />
        </label>
        <label>
          Currency
          <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {TOKENS.map((t) => (
              <option key={t.symbol} value={t.symbol}>{t.symbol}</option>
            ))}
          </select>
        </label>
        <label>
          Description <span className="muted small">(optional)</span>
          <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="delivery" />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="primary" type="submit">Create invoice</button>
      </form>
    </div>
  );
}
