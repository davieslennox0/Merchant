/** localStorage-backed ledger: invoices (inflows) + supplier payments (outflows).
 *  No backend — per hackathon scope. */

const INVOICES_KEY = "ma_invoices_v1";
const PAYMENTS_KEY = "ma_payments_v1";

// Payment detection tolerance, in dollars (same as the old WhatsApp build).
export const AMOUNT_TOLERANCE = 0.005;

// Invoices created before multi-token support have no currency field.
const currencyOf = (item) => item.currency || "cUSD";

function load(key) {
  try {
    return JSON.parse(localStorage.getItem(key)) || [];
  } catch {
    return [];
  }
}

function save(key, items) {
  localStorage.setItem(key, JSON.stringify(items));
}

export function getInvoices() {
  return load(INVOICES_KEY).sort((a, b) => b.createdAt - a.createdAt);
}

export function createInvoice({ customerName, amountCusd, description, currency = "cUSD" }) {
  const invoices = load(INVOICES_KEY);
  const invoice = {
    id: `inv_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    customerName,
    amountCusd: Number(amountCusd),
    currency,
    description: description || "",
    status: "pending",
    txHash: null,
    createdAt: Date.now(),
    paidAt: null,
  };
  invoices.push(invoice);
  save(INVOICES_KEY, invoices);
  return invoice;
}

export function markInvoicePaid(id, txHash) {
  const invoices = load(INVOICES_KEY);
  const inv = invoices.find((i) => i.id === id);
  if (!inv || inv.status === "paid") return null;
  inv.status = "paid";
  inv.txHash = txHash;
  inv.paidAt = Date.now();
  save(INVOICES_KEY, invoices);
  return inv;
}

/** Match an incoming stable transfer to the oldest pending invoice with the
 *  same currency and amount (within tolerance). A tx hash settles at most one
 *  invoice. */
export function matchTransferToInvoice(amountCusd, txHash, currency = "cUSD") {
  const invoices = load(INVOICES_KEY);
  if (invoices.some((i) => i.txHash === txHash)) return null; // already settled
  const candidates = invoices
    .filter(
      (i) =>
        i.status === "pending" &&
        currencyOf(i) === currency &&
        Math.abs(i.amountCusd - amountCusd) <= AMOUNT_TOLERANCE
    )
    .sort((a, b) => a.createdAt - b.createdAt);
  if (candidates.length === 0) return null;
  return markInvoicePaid(candidates[0].id, txHash);
}

export function getPayments() {
  return load(PAYMENTS_KEY).sort((a, b) => b.createdAt - a.createdAt);
}

export function recordSupplierPayment({ supplierName, address, amountCusd, txHash, currency = "cUSD" }) {
  const payments = load(PAYMENTS_KEY);
  const payment = {
    id: `pay_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    supplierName: supplierName || "Supplier",
    address,
    amountCusd: Number(amountCusd),
    currency,
    txHash,
    createdAt: Date.now(),
  };
  payments.push(payment);
  save(PAYMENTS_KEY, payments);
  return payment;
}

export function getStats() {
  const invoices = load(INVOICES_KEY);
  const payments = load(PAYMENTS_KEY);
  const paid = invoices.filter((i) => i.status === "paid");
  const pending = invoices.filter((i) => i.status === "pending");
  const income = paid.reduce((s, i) => s + i.amountCusd, 0);
  const owed = pending.reduce((s, i) => s + i.amountCusd, 0);
  const expenses = payments.reduce((s, p) => s + p.amountCusd, 0);
  return {
    invoices_paid: paid.length,
    invoices_pending: pending.length,
    income,
    owed,
    supplier_payments: payments.length,
    expenses,
    net: income - expenses,
  };
}

/** Unified ledger: inflows and outflows, newest first. */
export function getLedger() {
  const inflows = getInvoices()
    .filter((i) => i.status === "paid")
    .map((i) => ({
      id: i.id,
      type: "in",
      label: `Invoice — ${i.customerName}`,
      amountCusd: i.amountCusd,
      currency: currencyOf(i),
      txHash: i.txHash,
      at: i.paidAt || i.createdAt,
    }));
  const outflows = getPayments().map((p) => ({
    id: p.id,
    type: "out",
    label: `Supplier — ${p.supplierName}`,
    amountCusd: p.amountCusd,
    currency: currencyOf(p),
    txHash: p.txHash,
    at: p.createdAt,
  }));
  return [...inflows, ...outflows].sort((a, b) => b.at - a.at);
}
