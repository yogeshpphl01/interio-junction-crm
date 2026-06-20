/*
  <component name="CloseLeadModal" layer="frontend">
    <purpose>Capture a lead outcome — Won / Lost / On-hold (or reopen to Active) —
    via POST /leads/{id}/close. A Lost reason is required; Won can record a value.
    This is what drives the lead's lifecycle bucket to Completed / Dropped.</purpose>
  </component>
*/
import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const ACTIONS = [
  { key: "Won", label: "Mark as Won", color: "#4A5D23", description: "Project signed and accepted." },
  { key: "Lost", label: "Mark as Lost", color: "#A95A3F", description: "Lead dropped — capture why so we learn from it." },
  { key: "On-hold", label: "Put on Hold", color: "#8A817C", description: "Pause but keep in pipeline." },
];

const LOST_REASONS = [
  "Budget mismatch",
  "Chose competitor",
  "Timeline mismatch",
  "Site unfit / location issue",
  "Out of scope (not modular)",
  "No response / ghosted",
  "Other",
];

export default function CloseLeadModal({ lead, onClose, onClosed }) {
  const [status, setStatus] = useState(lead.status === "Active" ? "Won" : "Active");
  const [reason, setReason] = useState("");
  const [lostPreset, setLostPreset] = useState(LOST_REASONS[0]);
  const [wonValue, setWonValue] = useState(lead.tentative_budget || 0);
  const [busy, setBusy] = useState(false);

  const isReopen = lead.status !== "Active" && status === "Active";

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      let finalReason = reason.trim();
      if (status === "Lost") {
        finalReason = lostPreset === "Other" ? finalReason : `${lostPreset}${finalReason ? ` — ${finalReason}` : ""}`;
        if (!finalReason) {
          toast.error("Please give a reason for Lost.");
          setBusy(false);
          return;
        }
      }
      const payload = { status, reason: finalReason };
      if (status === "Won") payload.won_value = Number(wonValue) || lead.tentative_budget;
      const { data } = await api.post(`/leads/${lead.id}/close`, payload);
      toast.success(isReopen ? "Lead reopened" : `Marked ${status}`);
      onClosed(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-bone-paper border border-edge rounded-md w-full max-w-lg max-h-[90vh] overflow-y-auto scrollbar-thin" data-testid="close-lead-modal">
        <div className="px-5 py-4 border-b border-edge flex justify-between">
          <div>
            <h3 className="font-serif text-xl text-ink">{isReopen ? "Reopen lead" : "Close lead"}</h3>
            <div className="text-xs text-ink-muted mt-0.5">{lead.full_name}</div>
          </div>
          <button onClick={onClose} className="text-2xl text-ink-soft leading-none" data-testid="close-lead-modal-close">×</button>
        </div>

        <form onSubmit={submit} className="p-5 space-y-4">
          {lead.status === "Active" ? (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold mb-2">Outcome</div>
              <div className="grid grid-cols-3 gap-2">
                {ACTIONS.map((a) => (
                  <button
                    type="button"
                    key={a.key}
                    onClick={() => setStatus(a.key)}
                    data-testid={`close-status-${a.key.toLowerCase()}`}
                    className={`border rounded-md p-3 text-left transition ${status === a.key ? "border-clay bg-clay/5" : "border-edge bg-bone-paper hover:bg-bone"}`}
                  >
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: a.color }} />
                      <span className="text-sm font-medium text-ink">{a.label.replace("Mark as ", "").replace("Put ", "")}</span>
                    </div>
                    <div className="text-[10px] text-ink-muted leading-snug">{a.description}</div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-bone-subtle border border-edge rounded-md p-3 text-sm text-ink-soft">
              Currently marked <strong>{lead.status}</strong>. Reopen will set status back to Active.
            </div>
          )}

          {status === "Won" && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold mb-1">Won at value (₹)</div>
              <input
                type="number"
                min={0}
                value={wonValue}
                onChange={(e) => setWonValue(e.target.value)}
                data-testid="won-value-input"
                className={inp}
              />
              <div className="text-[11px] text-ink-muted mt-1">Defaults to tentative budget; adjust to your signed contract value.</div>
            </div>
          )}

          {status === "Lost" && (
            <>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold mb-1">Primary reason</div>
                <select
                  value={lostPreset}
                  onChange={(e) => setLostPreset(e.target.value)}
                  data-testid="lost-preset"
                  className={inp}
                >
                  {LOST_REASONS.map((r) => <option key={r}>{r}</option>)}
                </select>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold mb-1">
                  {lostPreset === "Other" ? "Describe the reason" : "Add context (optional)"}
                </div>
                <textarea
                  rows={3}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="What did you learn from this loss?"
                  data-testid="close-reason"
                  className={inp}
                />
              </div>
            </>
          )}

          {(status === "On-hold" || status === "Active") && status !== "Won" && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold mb-1">
                Reason / Note {status === "On-hold" ? "" : "(optional)"}
              </div>
              <textarea
                rows={3}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={status === "On-hold" ? "When should we follow up?" : "Why are we reopening this?"}
                data-testid="close-reason"
                className={inp}
              />
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-edge">
            <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
            <button
              type="submit"
              disabled={busy}
              data-testid="confirm-close-lead"
              className="bg-clay hover:bg-clay-deep text-white px-3 py-1.5 text-sm rounded disabled:opacity-50"
            >
              {busy ? "Saving…" : isReopen ? "Reopen lead" : `Mark ${status}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const inp = "w-full bg-bone-paper border border-edge rounded-md px-3 py-2 text-ink text-sm focus:border-clay outline-none";
