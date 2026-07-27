import { useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { UploadCloud, FileSpreadsheet, CheckCircle2 } from "lucide-react";

/*
  <component name="ImportLeadsModal" layer="frontend">
    <purpose>
      Lets an admin/sales user upload a Meta (Facebook/Instagram) "Lead Ads"
      Excel/CSV export. The file is POSTed to /api/imports/leads, which upserts
      the rows into PostgreSQL and returns a summary (created/updated/skipped).
    </purpose>
    <flow>
      pick file -> Upload -> show busy -> render result summary -> onImported()
      refreshes the Leads table. Re-uploading the same file is safe (idempotent
      on the backend via meta_lead_id).
    </flow>
  </component>
*/
export default function ImportLeadsModal({ onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (!file) {
      toast.error("Choose a spreadsheet first");
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      // NOTE: do not set Content-Type manually — the browser adds the multipart
      // boundary. The api interceptor still attaches the auth bearer token.
      const { data } = await api.post("/imports/leads", fd);
      setResult(data);
      toast.success(`Imported: ${data.created} new, ${data.updated} updated`);
      onImported && onImported(data);
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Import failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-bone-paper rounded-md border border-edge w-full max-w-xl max-h-[90vh] overflow-y-auto scrollbar-thin"
        data-testid="import-leads-modal"
      >
        <div className="px-6 py-5 border-b border-edge flex items-center justify-between">
          <h3 className="font-serif text-2xl text-ink">Import Leads</h3>
          <button onClick={onClose} className="text-ink-soft hover:text-ink text-2xl leading-none" data-testid="import-modal-close">×</button>
        </div>

        {/* <section name="result-summary"> shown after a successful upload */}
        {result ? (
          <div className="px-6 py-6">
            <div className="flex items-center gap-2 text-walnut mb-4">
              <CheckCircle2 className="w-5 h-5 text-[#4A5D23]" />
              <span className="font-medium text-ink">Import complete</span>
            </div>
            <div className="grid grid-cols-4 gap-3 mb-4">
              <Stat label="Created" value={result.created} accent="#4A5D23" />
              <Stat label="Updated" value={result.updated} accent="#9C6644" />
              <Stat label="Skipped" value={result.skipped} accent="#6B705C" />
              <Stat label="Errors" value={result.errors?.length || 0} accent="#A95A3F" />
            </div>
            <div className="text-xs text-ink-muted mb-4">
              {result.total_rows} rows read from <span className="font-medium text-ink-soft">{result.filename}</span>.
            </div>
            {result.errors?.length > 0 && (
              <div className="border border-edge rounded-md p-3 mb-4 max-h-40 overflow-y-auto scrollbar-thin">
                <div className="text-[11px] uppercase tracking-wide text-ink-muted font-semibold mb-2">Row errors</div>
                {result.errors.map((er, i) => (
                  <div key={i} className="text-xs text-ink-soft">Row {er.row}: {er.reason}</div>
                ))}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => { setResult(null); setFile(null); }} className="px-4 py-2 text-ink-soft hover:text-ink text-sm">Import another</button>
              <button onClick={onClose} className="bg-clay hover:bg-clay-deep text-white rounded-md px-4 py-2 text-sm font-medium">Done</button>
            </div>
          </div>
        ) : (
          <form className="px-6 py-5" onSubmit={submit}>
            <p className="text-sm text-ink-soft mb-4">
              Upload a <span className="font-medium">Meta Lead Ads</span> export (<code className="text-xs">.xlsx</code> or <code className="text-xs">.csv</code>).
              Existing leads are matched by their Meta lead id and refreshed without losing pipeline progress.
            </p>

            {/* <file-picker> styled drop zone */}
            <label className="block border-2 border-dashed border-edge rounded-md px-4 py-8 text-center cursor-pointer hover:border-clay transition-colors" data-testid="import-dropzone">
              <input
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                data-testid="import-file-input"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
              {file ? (
                <div className="flex flex-col items-center gap-2 text-ink">
                  <FileSpreadsheet className="w-8 h-8 text-clay" />
                  <span className="text-sm font-medium">{file.name}</span>
                  <span className="text-[11px] text-ink-muted">{(file.size / 1024).toFixed(0)} KB · click to change</span>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2 text-ink-muted">
                  <UploadCloud className="w-8 h-8" />
                  <span className="text-sm">Click to choose a file</span>
                </div>
              )}
            </label>

            <div className="flex items-center justify-end gap-2 pt-5 mt-5 border-t border-edge">
              <button type="button" onClick={onClose} className="px-4 py-2 text-ink-soft hover:text-ink text-sm">Cancel</button>
              <button
                type="submit"
                disabled={busy || !file}
                data-testid="submit-import"
                className="bg-clay hover:bg-clay-deep disabled:opacity-50 text-white rounded-md px-4 py-2 text-sm font-medium"
              >
                {busy ? "Importing…" : "Import"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, accent }) {
  return (
    <div className="rounded-md border border-edge p-3 text-center">
      <div className="font-serif text-2xl leading-none" style={{ color: accent }}>{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-ink-muted mt-1">{label}</div>
    </div>
  );
}
