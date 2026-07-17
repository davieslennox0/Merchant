import { useState } from "react";
import { useMiniPay } from "./lib/useMiniPay";
import { usePaymentWatcher } from "./lib/usePaymentWatcher";
import Dashboard from "./screens/Dashboard";
import NewInvoice from "./screens/NewInvoice";
import Invoices from "./screens/Invoices";
import PaySupplier from "./screens/PaySupplier";
import Ledger from "./screens/Ledger";
import Agent from "./screens/Agent";

const TABS = [
  ["home", "Home"],
  ["invoices", "Invoices"],
  ["agent", "Agent"],
  ["ledger", "Ledger"],
];

export default function App() {
  const { address, isMiniPay, hasProvider } = useMiniPay();
  const [screen, setScreen] = useState("home");
  const [prefill, setPrefill] = useState(null);
  const [toast, setToast] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  usePaymentWatcher(address, (invoice) => {
    setToast(`💰 ${invoice.customerName} paid ${invoice.amountCusd.toFixed(2)} cUSD`);
    setRefreshKey((k) => k + 1);
    setTimeout(() => setToast(null), 6000);
  });

  const go = (next, withPrefill = null) => {
    setPrefill(withPrefill);
    setScreen(next);
  };

  return (
    <div className="app">
      <header className="topbar">
        <span className="logo">🛍️ Merchant Agent</span>
        {isMiniPay ? (
          <span className="pill paid">MiniPay</span>
        ) : (
          <span className="pill pending">browser</span>
        )}
      </header>

      {!hasProvider && (
        <div className="banner">
          MiniPay not detected. Open this page inside MiniPay (compass icon → Test
          Page) to connect your wallet automatically.
        </div>
      )}

      {toast && <div className="toast">{toast}</div>}

      <main>
        {screen === "home" && <Dashboard address={address} isMiniPay={isMiniPay} go={go} />}
        {screen === "new" && <NewInvoice address={address} go={go} prefill={prefill} />}
        {screen === "invoices" && <Invoices go={go} refreshKey={refreshKey} />}
        {screen === "pay" && <PaySupplier isMiniPay={isMiniPay} go={go} prefill={prefill} />}
        {screen === "ledger" && <Ledger refreshKey={refreshKey} />}
        {screen === "agent" && <Agent go={go} />}
      </main>

      <nav className="tabbar">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            className={screen === id ? "tab active" : "tab"}
            onClick={() => go(id)}
          >
            {label}
          </button>
        ))}
      </nav>
    </div>
  );
}
