import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { History, RotateCcw } from "lucide-react";
import { toast } from "sonner";

export default function Audit() {
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const load = () => api.get("/audit", { params: { page, page_size: 30 } }).then(({ data }) => setData(data));
  useEffect(() => { load(); }, [page]);

  const rollback = async (a) => {
    if (a.resource_type !== "product") { toast.error("Rollback available for products here"); return; }
    try { await api.post(`/products/${a.resource_id}/rollback`); toast.success("Rolled back"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div className="space-y-5">
      <div><h1 className="font-heading text-3xl font-bold tracking-tight">Audit & Rollback</h1>
        <p className="mt-1 text-sm text-muted-foreground">Every published SEO change is immutably recorded with previous values for rollback.</p></div>

      {data?.items.length === 0 && <div className="rounded-xl border border-dashed border-border py-16 text-center text-muted-foreground"><History className="mx-auto mb-3 h-8 w-8" />No SEO changes published yet.</div>}

      <div className="space-y-3">
        {data?.items.map((a) => (
          <div key={a.id} data-testid="audit-row" className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-start justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] uppercase">{a.source}</span>
                  <span className="font-medium">{a.resource_title}</span>
                  <span className="text-[11px] text-muted-foreground">({a.resource_type})</span>
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">{a.user} • {new Date(a.timestamp).toLocaleString()} • {a.result}</div>
                <div className="mt-2 space-y-1.5">
                  {a.changes?.map((c, i) => (
                    <div key={i} className="text-xs">
                      <span className="font-mono uppercase text-muted-foreground">{c.field}:</span>{" "}
                      <span className="text-rose-400 line-through">{c.old || "(empty)"}</span>{" → "}
                      <span className="text-emerald-400">{c.new || "(empty)"}</span>
                    </div>
                  ))}
                </div>
              </div>
              {can("rollback") && !a.reverted && a.source !== "Rollback" && (
                <button data-testid="audit-log-rollback-btn" onClick={() => rollback(a)}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent">
                  <RotateCcw className="h-3.5 w-3.5" /> Rollback
                </button>
              )}
              {a.reverted && <span className="shrink-0 text-[11px] text-muted-foreground">reverted</span>}
            </div>
          </div>
        ))}
      </div>

      {data && data.total > 30 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>page {page}</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40">Prev</button>
            <button disabled={page * 30 >= data.total} onClick={() => setPage((p) => p + 1)} className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40">Next</button>
          </div>
        </div>
      )}
    </div>
  );
}
