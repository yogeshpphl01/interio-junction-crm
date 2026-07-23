/*
  Documents — customer-safe files (renders, CAD, design files, quotations, site
  photos). Internal manufacturing docs are filtered out by the backend. Download
  goes through a short-lived signed URL (GET /client/documents/{id}/signed-url).
*/
import { FolderOpen, Download, FileText, Image, FileBox } from "lucide-react";
import { api, apiError, assetUrl } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useToast } from "@/components/Toast";
import { Badge, Card, Empty, PageLoader } from "@/components/ui";
import { shortDate } from "@/lib/format";

function iconFor(type, contentType) {
  if ((contentType || "").startsWith("image/") || type === "3D Render" || type === "Site Photo") return Image;
  if (type === "2D CAD" || type === "Design File") return FileBox;
  return FileText;
}

function prettySize(bytes) {
  const n = Number(bytes || 0);
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Documents() {
  const { data, loading, error } = useApi("/client/documents");
  const { push } = useToast();
  const documents = data?.documents || [];

  async function download(doc) {
    try {
      const { data } = await api.get(`/client/documents/${doc.id}/signed-url`);
      window.open(assetUrl(data.url), "_blank", "noopener");
    } catch (e) {
      push({ title: "Couldn't open file", description: apiError(e), tone: "error" });
    }
  }

  if (loading) return <PageLoader />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Documents</h1>
        <p className="mt-1 text-slate-500">Renders, drawings, quotations and photos shared with you.</p>
      </div>

      {error ? (
        <Empty icon={FolderOpen} title="Couldn't load documents" hint={error} />
      ) : documents.length === 0 ? (
        <Empty icon={FolderOpen} title="No documents yet" hint="Files your team shares will show up here." />
      ) : (
        <Card>
          <ul className="divide-y divide-slate-100">
            {documents.map((doc) => {
              const Icon = iconFor(doc.type, doc.content_type);
              return (
                <li key={doc.id} className="flex items-center gap-3 px-4 py-3.5">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-slate-800">{doc.filename || doc.type}</p>
                    <p className="mt-0.5 flex items-center gap-2 text-xs text-slate-400">
                      <Badge tone="brand">{doc.type}</Badge>
                      <span>{shortDate(doc.created_at)}</span>
                      {prettySize(doc.size) && <span>· {prettySize(doc.size)}</span>}
                    </p>
                  </div>
                  <button
                    onClick={() => download(doc)}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-brand-700 hover:bg-brand-50"
                  >
                    <Download className="h-4 w-4" /> <span className="hidden sm:inline">Download</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </div>
  );
}
