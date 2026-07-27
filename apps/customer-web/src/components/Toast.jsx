/* Minimal toast system (no dependency). useToast().push({ title, tone }). */
import { createContext, useCallback, useContext, useState } from "react";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

const ToastCtx = createContext(null);
const ICONS = { success: CheckCircle2, error: AlertCircle, info: Info };
const RING = {
  success: "border-emerald-200",
  error: "border-rose-200",
  info: "border-slate-200",
};

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);

  const push = useCallback(({ title, description, tone = "info", ttl = 4000 }) => {
    const id = Math.random().toString(36).slice(2);
    setItems((xs) => [...xs, { id, title, description, tone }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), ttl);
  }, []);

  const dismiss = useCallback((id) => setItems((xs) => xs.filter((x) => x.id !== id)), []);

  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
        {items.map((t) => {
          const Icon = ICONS[t.tone] || Info;
          return (
            <div
              key={t.id}
              className={cn(
                "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border bg-white px-4 py-3 shadow-card",
                RING[t.tone]
              )}
            >
              <Icon
                className={cn(
                  "mt-0.5 h-5 w-5 shrink-0",
                  t.tone === "success" && "text-emerald-600",
                  t.tone === "error" && "text-rose-600",
                  t.tone === "info" && "text-slate-500"
                )}
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-900">{t.title}</p>
                {t.description && <p className="mt-0.5 text-sm text-slate-500">{t.description}</p>}
              </div>
              <button onClick={() => dismiss(t.id)} className="text-slate-400 hover:text-slate-600">
                <X className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
