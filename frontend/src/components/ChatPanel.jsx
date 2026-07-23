/*
  <component name="ChatPanel" layer="frontend">
    <purpose>
      Staff side of the project chat (the customer's counterpart lives in the
      client portal). Ensures the project thread exists (POST /chat/threads,
      create-or-return), lists messages, polls (8s), and sends. Staff messages
      sit on the right (clay), the customer's on the left. Gated by chat.access.
    </purpose>
  </component>
*/
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Send } from "lucide-react";

function ago(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export default function ChatPanel({ projectId, customerName }) {
  const [thread, setThread] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef(null);

  // Create-or-return the project's thread.
  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    (async () => {
      try {
        const { data } = await api.post("/chat/threads", { project_id: projectId, kind: "dm" });
        if (alive) setThread(data);
      } catch (e) {
        if (alive) setError(e?.response?.data?.detail || "Chat is unavailable for this project.");
      }
    })();
    return () => { alive = false; };
  }, [projectId]);

  const loadMessages = useCallback(async (tid) => {
    try {
      const { data } = await api.get(`/chat/threads/${tid}/messages`);
      setMessages(Array.isArray(data) ? data : []);
    } catch { /* transient; next poll retries */ }
  }, []);

  useEffect(() => {
    if (!thread?.id) return;
    loadMessages(thread.id);
    const t = setInterval(() => loadMessages(thread.id), 8000);
    return () => clearInterval(t);
  }, [thread?.id, loadMessages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const send = async (e) => {
    e.preventDefault();
    const body = draft.trim();
    if (!body || !thread?.id) return;
    setSending(true);
    try {
      const { data } = await api.post(`/chat/threads/${thread.id}/messages`, { body });
      setMessages((m) => [...m, data]);
      setDraft("");
    } catch (e) {
      setError(e?.response?.data?.detail || "Message not sent.");
    } finally {
      setSending(false);
    }
  };

  if (error && !thread) return <div className="text-sm text-ink-muted py-2">{error}</div>;

  return (
    <div className="flex flex-col h-80" data-testid="chat-panel">
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {messages.length === 0 ? (
          <div className="text-sm text-ink-muted py-8 text-center">
            No messages yet. Say hello to {customerName?.split(" ")[0] || "your client"}.
          </div>
        ) : (
          messages.map((m) => {
            const staff = m.sender_type === "staff";
            return (
              <div key={m.id} className={`flex ${staff ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-md px-3 py-1.5 ${staff ? "bg-clay text-white" : "bg-bone-subtle text-ink"}`}>
                  {!staff && <div className="text-[10px] text-ink-muted mb-0.5">{m.sender_name || "Client"}</div>}
                  <div className="whitespace-pre-wrap break-words text-sm">{m.body}</div>
                  <div className={`text-[10px] mt-0.5 ${staff ? "text-white/70 text-right" : "text-ink-muted"}`}>{ago(m.created_at)}</div>
                </div>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={send} className="mt-2 flex items-center gap-2">
        <input
          className="flex-1 bg-bone-paper border border-edge rounded-md px-3 py-2 text-sm text-ink focus:border-clay outline-none"
          placeholder="Message the client…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          data-testid="chat-input"
        />
        <button type="submit" disabled={!draft.trim() || sending} className="bg-clay text-white rounded-md p-2 disabled:opacity-50" data-testid="chat-send" title="Send">
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
}
