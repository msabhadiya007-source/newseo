import { useEffect, useState, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { StatusBadge, PubBadge } from "@/components/StatusBadge";
import { scoreColor } from "@/lib/seo";
import { Search, Lock, ChevronLeft, ChevronRight, Pencil, Package } from "lucide-react";

const TABS = [
  { key: "all", label: "All", testid: "all" },
  { key: "missing", label: "Missing SEO", testid: "missing" },
  { key: "critical", label: "Critical", testid: "critical" },
  { key: "needs_improvement", label: "Needs Improvement", testid: "needs-improvement" },
  { key: "good", label: "Good", testid: "good" },
  { key: "optimised", label: "Fully Optimised", testid: "optimised" },
  { key: "drafts", label: "Drafts", testid: "drafts" },
];

const ISSUES = [
  ["", "All issues"], ["MISSING_SEO_TITLE", "Missing Title"], ["MISSING_META_DESCRIPTION", "Missing Description"],
  ["TITLE_TOO_SHORT", "Title Too Short"], ["TITLE_ABOVE_RANGE", "Title Above Range"],
  ["META_TOO_SHORT", "Meta Too Short"], ["META_ABOVE_RANGE", "Meta Above Range"],
  ["DUPLICATE_TITLE", "Duplicate Titles"], ["DUPLICATE_META", "Duplicate Descriptions"],
  ["KEYWORD_STUFFING", "Keyword Stuffing"],
];

export default function Products() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [bucket, setBucket] = useState(params.get("bucket") || "all");
  const [issue, setIssue] = useState(params.get("issue") || "");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { const t = setTimeout(() => setDebounced(search), 350); return () => clearTimeout(t); }, [search]);
  useEffect(() => { setPage(1); }, [bucket, issue, debounced, pageSize]);

  const load = useCallback(() => {
    setLoading(true);
    api.get("/products", { params: { bucket, issue: issue || undefined, search: debounced || undefined, page, page_size: pageSize } })
      .then(({ data }) => setData(data)).finally(() => setLoading(false));
  }, [bucket, issue, debounced, page, pageSize]);
  useEffect(() => { load(); }, [load]);

  const tabs = data?.tabs || {};
  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading text-3xl font-bold tracking-tight">Products SEO Queues</h1>
        <p className="mt-1 text-sm text-muted-foreground">Edit SEO title & meta description only. Commerce fields are locked.</p>
      </div>

      <div className="flex flex-wrap gap-1.5 border-b border-border pb-3">
        {TABS.map((t) => (
          <button key={t.key} data-testid={`products-queue-tab-${t.testid}`}
            onClick={() => { setBucket(t.key); setIssue(""); setParams({}); }}
            className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              bucket === t.key ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent"}`}>
            {t.label}
            <span className="rounded-full bg-muted px-1.5 py-0.5 font-mono text-[10px]">
              {(tabs[t.key] ?? 0).toLocaleString()}
            </span>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input data-testid="products-table-search-input" value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title, handle, product ID, SEO title…"
            className="w-full rounded-md border border-input bg-background py-2 pl-9 pr-3 text-sm outline-none focus:border-primary" />
        </div>
        <select data-testid="products-issue-filter" value={issue} onChange={(e) => setIssue(e.target.value)}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary">
          {ISSUES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select data-testid="products-page-size-select" value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary">
          {[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n} / page</option>)}
        </select>
      </div>

      <div className="overflow-hidden rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead className="bg-card text-left text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
            <tr>
              <th className="px-4 py-3">Product</th>
              <th className="px-4 py-3">SEO Title</th>
              <th className="px-4 py-3">Meta Description</th>
              <th className="px-4 py-3 text-center">Score</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading && <tr><td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">Loading…</td></tr>}
            {!loading && data?.items.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-16 text-center text-muted-foreground">
                <Package className="mx-auto mb-3 h-8 w-8" /> No products in this queue.
              </td></tr>
            )}
            {!loading && data?.items.map((p) => (
              <tr key={p.id} data-testid="products-table-row"
                className="cursor-pointer bg-background transition-colors hover:bg-accent/50"
                onClick={() => navigate(`/products/${p.id}`)}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 shrink-0 overflow-hidden rounded-md bg-muted">
                      {p.images?.[0]?.src && <img src={p.images[0].src} alt="" className="h-full w-full object-cover" />}
                    </div>
                    <div className="min-w-0">
                      <div className="truncate font-medium">{p.title}</div>
                      <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                        <Lock className="h-2.5 w-2.5" /> ${p.price} • {p.inventory} in stock
                      </div>
                    </div>
                  </div>
                </td>
                <td className="max-w-[220px] px-4 py-3">
                  <div className="truncate text-muted-foreground">{p.current_seo_title || <span className="text-rose-400">— missing —</span>}</div>
                  {p.current_seo_title && <div className="font-mono text-[10px] text-muted-foreground">{p.current_seo_title.length} chars</div>}
                </td>
                <td className="max-w-[240px] px-4 py-3">
                  <div className="truncate text-muted-foreground">{p.current_seo_description || <span className="text-rose-400">— missing —</span>}</div>
                  {p.current_seo_description && <div className="font-mono text-[10px] text-muted-foreground">{p.current_seo_description.length} chars</div>}
                </td>
                <td className="px-4 py-3 text-center">
                  <span className="font-mono font-bold" style={{ color: scoreColor(p.seo_score) }}>{p.seo_score}</span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-col gap-1">
                    <StatusBadge bucket={p.status_bucket} />
                    {p.has_draft && <PubBadge status="draft" />}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <button data-testid="products-table-edit-button"
                    className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs hover:bg-accent">
                    <Pencil className="h-3 w-3" /> Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{data.total.toLocaleString()} products • page {page} of {totalPages}</span>
          <div className="flex items-center gap-2">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
              className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 disabled:opacity-40">
              <ChevronLeft className="h-4 w-4" /> Prev
            </button>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}
              className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 disabled:opacity-40">
              Next <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
