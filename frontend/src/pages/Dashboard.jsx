import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import ScoreDial from "@/components/ScoreDial";
import { Boxes, CheckCircle2, AlertTriangle, XCircle, TrendingUp, RefreshCw, ArrowRight } from "lucide-react";

function Metric({ testid, label, value, sub, icon: Icon, tone }) {
  const toneMap = {
    green: "text-emerald-400", amber: "text-amber-400", rose: "text-rose-400",
    sky: "text-sky-400", default: "text-foreground",
  };
  return (
    <div data-testid={testid} className="rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/40">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{label}</span>
        <Icon className={`h-4 w-4 ${toneMap[tone] || toneMap.default}`} />
      </div>
      <div className={`mt-3 font-mono text-3xl font-bold tracking-tight ${toneMap[tone] || toneMap.default}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [m, setM] = useState(null);
  const navigate = useNavigate();

  const load = () => api.get("/dashboard/metrics").then(({ data }) => setM(data)).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 6000); return () => clearInterval(t); }, []);

  if (!m) return <div className="text-muted-foreground">Loading dashboard…</div>;

  const fmt = (n) => (n ?? 0).toLocaleString();
  const pct = (n) => (m.total ? Math.round((n / m.total) * 100) : 0);

  if (m.empty) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-24 text-center">
        <Boxes className="mb-4 h-12 w-12 text-muted-foreground" />
        <h2 className="font-heading text-2xl font-semibold">No products synced yet</h2>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          {m.connected ? "Run a sync to pull products from Shopify." : "Shopify is not connected. Run a demo sync to load the dev catalog and explore the SEO workflow."}
        </p>
        <button data-testid="dashboard-sync-cta" onClick={() => api.post("/sync").then(() => load())}
          className="mt-6 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">
          <RefreshCw className="h-4 w-4" /> Sync Now
        </button>
      </div>
    );
  }

  const issueEntries = Object.entries(m.issues || {}).sort((a, b) => b[1] - a[1]);
  const maxIssue = Math.max(1, ...issueEntries.map(([, v]) => v));

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">SEO Health Command</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Live analysis across {fmt(m.total)} products •{" "}
            <span className="font-mono uppercase">{m.data_source}</span> data source
          </p>
        </div>
        <div className="flex items-center gap-4 rounded-xl border border-border bg-card px-6 py-4">
          <ScoreDial score={m.health} size={90} stroke={9} testid="dashboard-seo-health-score" />
          <div className="leading-tight">
            <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Overall SEO Health</div>
            <div className="font-mono text-2xl font-bold">{m.health}%</div>
            <div className="mt-1 flex items-center gap-1 text-xs text-emerald-400"><TrendingUp className="h-3 w-3" /> deterministic + AI</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        <Metric testid="dashboard-metric-total-products" label="Total Products" value={fmt(m.total)} sub="Indexed & analyzed" icon={Boxes} />
        <Metric testid="dashboard-metric-fully-optimised" label="Fully Optimised" value={fmt(m.fully_optimised)} sub={`${pct(m.fully_optimised)}% of catalog`} icon={CheckCircle2} tone="green" />
        <Metric testid="dashboard-metric-good" label="Good" value={fmt(m.good)} sub={`${pct(m.good)}% of catalog`} icon={CheckCircle2} tone="green" />
        <Metric testid="dashboard-metric-needs-improvement" label="Needs Improvement" value={fmt(m.needs_improvement)} sub={`${pct(m.needs_improvement)}% of catalog`} icon={AlertTriangle} tone="amber" />
        <Metric testid="dashboard-metric-missing-seo" label="Missing SEO" value={fmt(m.missing_seo)} sub={`${pct(m.missing_seo)}% of catalog`} icon={XCircle} tone="rose" />
        <Metric testid="dashboard-metric-critical-issues" label="Critical Issues" value={fmt(m.critical)} sub={`${pct(m.critical)}% of catalog`} icon={XCircle} tone="rose" />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 rounded-xl border border-border bg-card p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-heading text-lg font-semibold">Issue Category Breakdown</h2>
            <button onClick={() => navigate("/products")} className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
              View queues <ArrowRight className="h-3 w-3" />
            </button>
          </div>
          <div className="space-y-3">
            {issueEntries.length === 0 && <p className="text-sm text-muted-foreground">No SEO issues found.</p>}
            {issueEntries.map(([code, count]) => (
              <button key={code} onClick={() => navigate(`/products?issue=${code}`)}
                data-testid={`dashboard-issue-${code}`}
                className="group flex w-full items-center gap-3 text-left">
                <span className="w-56 shrink-0 text-sm text-muted-foreground group-hover:text-foreground">
                  {m.issue_labels?.[code] || code}
                </span>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${(count / maxIssue) * 100}%` }} />
                </div>
                <span className="w-16 shrink-0 text-right font-mono text-sm">{fmt(count)}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-4 font-heading text-lg font-semibold">Quick Actions</h2>
          <div className="space-y-2">
            {[
              { l: "Fix Missing SEO", to: "/products?bucket=missing", c: "rose" },
              { l: "Review Critical Issues", to: "/products?bucket=critical", c: "rose" },
              { l: "Improve Needs-Work Items", to: "/products?bucket=needs_improvement", c: "amber" },
              { l: "Optimise Collections", to: "/collections", c: "sky" },
            ].map((a) => (
              <button key={a.to} onClick={() => navigate(a.to)}
                className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2.5 text-sm hover:bg-accent">
                {a.l} <ArrowRight className="h-4 w-4 text-muted-foreground" />
              </button>
            ))}
          </div>
          <div className="mt-4 rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
            Collections indexed: <span className="font-mono">{fmt(m.collections_total)}</span> • Drafts staged: <span className="font-mono">{fmt(m.drafts)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
