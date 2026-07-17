import { getStats } from "./invoices";

/** Calls the Groq-backed agent API (FastAPI behind /api on the same origin).
 *  Returns { intent, fields, reply }. */
export async function askAgent(message) {
  const resp = await fetch("/api/agent/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      context: {
        businessName: localStorage.getItem("ma_business_name") || "My Business",
        stats: getStats(),
      },
    }),
  });
  if (!resp.ok) throw new Error(`Agent API ${resp.status}`);
  return resp.json();
}
