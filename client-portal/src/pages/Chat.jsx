/*
  Messages — the customer's conversation with the Interio Junction team, scoped to
  their project thread(s). Threads are opened by staff; the customer reads and
  replies here. Endpoints: GET /client/chat, GET/POST /client/chat/{id}/messages.
  Light polling (8s) keeps the thread fresh without a websocket.
*/
import { useEffect, useRef, useState, useCallback } from "react";
import { MessageCircle, Send } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/components/Toast";
import { Empty, PageLoader, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";
import { dateTime } from "@/lib/format";

export default function Chat() {
  const { customer } = useAuth();
  const { push } = useToast();
  const [threads, setThreads] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);
  const bottomRef = useRef(null);

  // Load the customer's threads once.
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/client/chat");
        const list = data?.threads || [];
        setThreads(list);
        if (list.length) setActiveId(list[0].id);
      } catch {
        setThreads([]);
      }
    })();
  }, []);

  const loadMessages = useCallback(async (id, { quiet } = {}) => {
    if (!id) return;
    try {
      const { data } = await api.get(`/client/chat/${id}/messages`);
      setMessages(Array.isArray(data) ? data : []);
    } catch (e) {
      if (!quiet) push({ title: "Couldn't load messages", description: apiError(e), tone: "error" });
    }
  }, [push]);

  // Load + poll the active thread.
  useEffect(() => {
    if (!activeId) return;
    loadMessages(activeId);
    const t = setInterval(() => loadMessages(activeId, { quiet: true }), 8000);
    return () => clearInterval(t);
  }, [activeId, loadMessages]);

  // Keep the view pinned to the newest message.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  async function send(e) {
    e?.preventDefault();
    const body = draft.trim();
    if (!body || !activeId) return;
    setSending(true);
    try {
      const { data } = await api.post(`/client/chat/${activeId}/messages`, { body });
      setMessages((m) => [...m, data]);
      setDraft("");
    } catch (e) {
      push({ title: "Message not sent", description: apiError(e), tone: "error" });
    } finally {
      setSending(false);
    }
  }

  if (threads === null) return <PageLoader />;

  if (threads.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Messages</h1>
        <Empty icon={MessageCircle} title="No conversation yet" hint="Your project manager will start a chat here. You'll be able to reply as soon as they do." />
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col lg:h-[calc(100vh-6rem)]">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Messages</h1>
        {threads.length > 1 && (
          <select
            value={activeId || ""}
            onChange={(e) => setActiveId(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm"
          >
            {threads.map((t) => (
              <option key={t.id} value={t.id}>{t.title || "Project chat"}</option>
            ))}
          </select>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto rounded-2xl border border-slate-100 bg-white p-4">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            Say hello — your team will see it right away.
          </div>
        ) : (
          messages.map((m) => {
            const mine = m.sender_type === "customer";
            return (
              <div key={m.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
                <div className={cn("max-w-[80%] rounded-2xl px-3.5 py-2", mine ? "bg-brand-700 text-white" : "bg-slate-100 text-slate-800")}>
                  {!mine && m.sender_name && <p className="mb-0.5 text-xs font-medium text-brand-700">{m.sender_name}</p>}
                  <p className="whitespace-pre-wrap break-words text-sm">{m.body}</p>
                  <p className={cn("mt-1 text-right text-[10px]", mine ? "text-white/70" : "text-slate-400")}>{dateTime(m.created_at)}</p>
                </div>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={send} className="mt-3 flex items-center gap-2">
        <input
          className="h-12 flex-1 rounded-xl border border-slate-200 bg-white px-4 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
          placeholder="Write a message…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          type="submit"
          disabled={!draft.trim() || sending}
          className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-700 text-white transition-colors hover:bg-brand-800 disabled:opacity-50"
        >
          {sending ? <Spinner className="h-5 w-5 text-white" /> : <Send className="h-5 w-5" />}
        </button>
      </form>
    </div>
  );
}
