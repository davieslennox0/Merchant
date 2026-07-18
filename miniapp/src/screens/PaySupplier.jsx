import { useState } from "react";
import { erc20Abi, isAddress, parseUnits } from "viem";
import { useWriteContract, useWaitForTransactionReceipt } from "wagmi";
import { toDataSuffix } from "@celo/attribution-tags";
import { CUSD_TESTNET, CHAIN, TOKENS, tokenBySymbol, ATTRIBUTION_TAG } from "../lib/wagmi";
import { recordSupplierPayment } from "../lib/invoices";

const EXPLORER = CHAIN.blockExplorers?.default?.url || "https://celo-sepolia.blockscout.com";

export default function PaySupplier({ isMiniPay, go, prefill }) {
  const [supplierName, setSupplierName] = useState(prefill?.supplier_name || "");
  const [to, setTo] = useState(prefill?.supplier_address || "");
  const [amount, setAmount] = useState(prefill?.amount_cusd?.toString() || "");
  const [currency, setCurrency] = useState(prefill?.currency || "cUSD");
  const [error, setError] = useState("");
  const [recorded, setRecorded] = useState(false);

  const { writeContract, data: txHash, isPending, error: writeError, reset } = useWriteContract();
  const { isLoading: confirming, isSuccess: confirmed } = useWaitForTransactionReceipt({
    hash: txHash,
    query: { enabled: !!txHash },
  });

  if (confirmed && txHash && !recorded) {
    recordSupplierPayment({ supplierName, address: to, amountCusd: Number(amount), txHash, currency });
    setRecorded(true);
  }

  const submit = (e) => {
    e.preventDefault();
    const amt = Number(amount);
    const token = tokenBySymbol(currency);
    if (!isAddress(to)) return setError("Enter a valid 0x… address.");
    if (!amt || amt <= 0) return setError("Enter a positive amount.");
    setError("");
    writeContract({
      address: token.address,
      abi: erc20Abi,
      functionName: "transfer",
      args: [to, parseUnits(String(amt), token.decimals)],
      // ERC-8021 hackathon attribution tag — must ride on every transaction.
      dataSuffix: toDataSuffix(ATTRIBUTION_TAG),
      // MiniPay only supports legacy (type 0) transactions with cUSD as the
      // fee currency; the wallet fills fees, we just avoid EIP-1559 fields.
      ...(isMiniPay ? { feeCurrency: CUSD_TESTNET } : {}),
    });
  };

  if (confirmed && txHash) {
    return (
      <div className="screen">
        <div className="card success">
          <h3>Payment sent ✓</h3>
          <p>
            <b>{Number(amount).toFixed(2)} {currency}</b> → {supplierName || "supplier"}
          </p>
          <a className="small" href={`${EXPLORER}/tx/${txHash}`} target="_blank" rel="noreferrer">
            {txHash.slice(0, 14)}… ↗
          </a>
        </div>
        <div className="actions">
          <button className="primary" onClick={() => go("ledger")}>View ledger</button>
          <button onClick={() => { reset(); setRecorded(false); setAmount(""); }}>
            Pay another
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <h2>Pay supplier</h2>
      <form onSubmit={submit} className="form">
        <label>
          Supplier name <span className="muted small">(optional)</span>
          <input value={supplierName} onChange={(e) => setSupplierName(e.target.value)} placeholder="Maria" />
        </label>
        <label>
          Wallet address
          <input value={to} onChange={(e) => setTo(e.target.value)} placeholder="0x…" spellCheck={false} />
        </label>
        <label>
          Amount
          <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" placeholder="20" />
        </label>
        <label>
          Currency
          <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {TOKENS.map((t) => (
              <option key={t.symbol} value={t.symbol}>{t.symbol}</option>
            ))}
          </select>
        </label>
        {error && <p className="error">{error}</p>}
        {writeError && (
          <p className="error">
            Transaction failed: {writeError.shortMessage || writeError.message}
          </p>
        )}
        <button className="primary" type="submit" disabled={isPending || confirming}>
          {isPending ? "Confirm in wallet…" : confirming ? "Confirming on-chain…" : `Send ${currency}`}
        </button>
      </form>
    </div>
  );
}
