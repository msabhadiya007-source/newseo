import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Activity, CheckCircle2, XCircle, Loader2, Clock } from "lucide-react";

const statusIcon = {
  completed: <CheckCircle2 className="h-4 w-4 text-emerald-400" />,
  failed: <XCircle className="h-4 w-4 text-rose-400" />,
  running: <Loader2 className="h-4 w-4 animate-spin text-sky-400" />,
  queued: <Clock className="h-4 w-4 text-slate-400" />,
};

export default function Jobs() {
  const [items, setItems] = useState([]);
  const load = () => api.get("/jobs").then(({ data }) => setItems(data.items)).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t); }, []);

  return (
    <div className="space-y-5">
      <div><h1 className="font-heading text-3xl font-bold tracking-tight">Job Center</h1>
        <p className="mt-1 text-sm text-muted-foreground">Background tasks persist across restarts. Progress is read from the database.</p></div>

      {items.length === 0 && <div className="rounded-xl border border-dashed border-border py-16 text-center text-muted-foreground"><Activity className="mx-auto mb-3 h-8 w-8" />No jobs yet.</div>}

      <div className="space-y-3">
        {items.map((j) => (
          <div key={j.id} data-testid="job-row" className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {statusIcon[j.status]}
                <div>
                  <div className="font-medium">{j.type} <span className="ml-1 font-mono text-xs text-muted-foreground">{j.id}</span></div>
                  <div className="text-xs text-muted-foreground">by {j.created_by} • {new Date(j.created_at).toLocaleString()}</div>
                </div>
              </div>
              <div className="text-right text-xs text-muted-foreground">
                <div>✓ {j.success} • ⚠ {j.warning} • ✕ {j.failed}</div>
                <div className="font-mono">{j.total} records</div>
              </div>
            </div>
            {(j.status === "running" || j.status === "queued") && (
              <div data-testid="job-center-active-progress" className="mt-3 h-2 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-sky-500 transition-all" style={{ width: `${j.progress}%` }} />
              </div>
            )}
            {j.message && <div className="mt-2 text-xs text-muted-foreground">{j.message}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
