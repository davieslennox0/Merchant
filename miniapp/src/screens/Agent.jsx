import { useRef, useState } from "react";
import { askAgent } from "../lib/agent";

const SUGGESTIONS = [
  "Invoice John 50 cUSD for delivery",
  "How am I doing this month?",
  "Pay Maria 20 cUSD",
];

export default function Agent({ go }) {
  const [messages, setMessages] = useState([
    {
      role: "agent",
      text: "Hi! I'm your merchant agent. Tell me things like “invoice John 50 for delivery”, “pay Maria 20 cUSD”, or ask how your business is doing.",
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef(null);

  const send = async (text) => {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: message }]);
    setBusy(true);
    try {
      const { intent, fields, reply } = await askAgent(message);
      const actions = [];
      if (intent === "create_invoice") {
        actions.push({ label: "Create this invoice →", screen: "new", prefill: fields });
      } else if (intent === "pay_supplier") {
        actions.push({ label: "Review & send payment →", screen: "pay", prefill: fields });
      }
      setMessages((m) => [...m, { role: "agent", text: reply, actions }]);
    } catch {
      setMessages((m) => [
        ...m,
        { role: "agent", text: "Sorry, I couldn't reach the agent service. Try again in a moment." },
      ]);
    } finally {
      setBusy(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  return (
    <div className="screen chat-screen">
      <div className="chat">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.text}
            {m.actions?.map((a) => (
              <button key={a.label} className="primary chat-action" onClick={() => go(a.screen, a.prefill)}>
                {a.label}
              </button>
            ))}
          </div>
        ))}
        {busy && <div className="bubble agent muted">thinking…</div>}
        <div ref={bottomRef} />
      </div>
      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="chip" onClick={() => send(s)} disabled={busy}>
            {s}
          </button>
        ))}
      </div>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message your agent…"
          disabled={busy}
        />
        <button className="primary" type="submit" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
