import { Fragment, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import PdfViewer from "../components/PdfViewer";
import { api } from "../lib/api";
import type { ChatTurn, Citation } from "../lib/types";

interface UiMessage extends ChatTurn {
  citations?: Citation[];
}

/** Render "[1]" markers in the answer as clickable citation buttons. */
function renderWithCitations(text: string, citations: Citation[], open: (c: Citation) => void): ReactNode[] {
  return text.split(/(\[\d+(?:\s*,\s*\d+)*\])/g).map((part, i) => {
    const match = part.match(/^\[(.+)\]$/);
    if (!match) return <Fragment key={i}>{part}</Fragment>;
    const nums = match[1].split(",").map((n) => Number(n.trim()));
    return (
      <Fragment key={i}>
        {nums.map((n) => {
          const c = citations.find((x) => x.index === n);
          return c ? (
            <button key={n} className="cite" onClick={() => open(c)} title={`${c.title ?? "Source"}, p.${c.page}`}>
              {n}
            </button>
          ) : (
            <Fragment key={n}>[{n}]</Fragment>
          );
        })}
      </Fragment>
    );
  });
}

export default function ChatPage() {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<Citation | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), [messages, busy]);

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    const question = input.trim();
    if (!question || busy) return;
    const history: ChatTurn[] = messages.map(({ role, content }) => ({ role, content }));
    setMessages((m) => [...m, { role: "user", content: question }]);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const res = await api.chat.send(question, history);
      setMessages((m) => [...m, { role: "assistant", content: res.answer, citations: res.citations }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chat">
      <h1>Tutor Chat</h1>
      <p className="muted small" style={{ marginTop: -8 }}>
        Answers come only from your textbooks and study materials, with citations you can click to open the exact page.
      </p>
      <div className="messages card">
        {messages.length === 0 && <p className="muted">Ask a question about anything in your study materials.</p>}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "assistant" ? renderWithCitations(m.content, m.citations ?? [], setViewing) : m.content}
            {!!m.citations?.length && (
              <div className="citations">
                {m.citations.map((c) => (
                  <button key={c.index} onClick={() => setViewing(c)}>
                    [{c.index}] {c.title ?? "Source"} — page {c.page}:{" "}
                    <span className="muted">“{c.excerpt.slice(0, 110)}…”</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="msg assistant muted">Thinking…</div>}
        <div ref={bottom} />
      </div>
      {error && <p className="error">{error}</p>}
      <form className="composer" onSubmit={send}>
        <textarea
          value={input}
          placeholder="e.g. Explain Newton's second law with an example"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
      {viewing && (
        <PdfViewer
          docId={viewing.doc_id}
          page={viewing.page}
          excerpt={viewing.excerpt}
          title={viewing.title}
          onClose={() => setViewing(null)}
        />
      )}
    </div>
  );
}
