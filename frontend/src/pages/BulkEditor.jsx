import React, { useEffect, useMemo, useState, useCallback } from "react";
import {
  Table2, Save, ShieldCheck, AlertTriangle, XCircle, CheckCircle2, Lock,
  Rocket, RotateCcw, RefreshCw, Ban, ChevronLeft, ChevronRight, Search, X, Eye,
} from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

const RANGES = { title_min: 50, title_max: 60, meta_min: 140, meta_max: 160 };
const PAGE_SIZES = [25, 50, 100, 200];
const BUCKETS = ["all", "missing", "critical", "needs_improvement", "good", "optimised"];

function counterState(len, min, max) {
  if (len === 0) return "empty";
  if (len > max) return "over";
  if (len < min) return "under";
  return "good";
}
const CTAG = { empty: "text-muted-foreground", under: "text-amber-500", over: "text-rose-500", good: "text-emerald-500" };

function Counter({ value, min, max }) {
  const len = (value || "").length;
  const st = counterState(len, min, max);
  return <span className={`font-mono text-[10px] ${CTAG[st]}`} title={`Recommended ${min}-${max}`}>{len}</span>;
}

const CONFLICT_LABEL = { none: null, shopify_changed: "Shopify changed", resource_deleted: "Deleted in Shopify" };

export default function BulkEditor() {
  const { can } = useAuth();
  const [rtype, setRtype] = useState("product");
  const [rules, setRules] = useState(RANGES);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [bucket, setBucket] = useState("all");
  const [missing, setMissing] = useState("");
  const [search, setSearch] = useState("");
  const [onlyDrafts, setOnlyDrafts] = useState(false);
  const [onlyConflicts, setOnlyConflicts] = useState(false);

  const [drafts, setDrafts] = useState({});
  const [selected, setSelected] = useState(new Set());
  const [allFiltered, setAllFiltered] = useState(false);
  const [preview, setPreview] = useState(null);
  const [allowWarnings, setAllowWarnings] = useState(false);
  const [validation, setValidation] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [conflictRow, setConflictRow] = useState(null);
  const [itemsModal, setItemsModal] = useState(null);

  const dirty = Object.keys(drafts).length > 0;

  useEffect(() => {
    api.get("/settings").then(({ data }) => setRules({ ...RANGES, ...(data.rules || {}) })).catch(() => {});
  }, []);

  useEffect(() => {
    const h = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const path = rtype === "product" ? "/bulk/products" : "/bulk/collections";
      const params = { page, page_size: pageSize, bucket };
      if (rtype === "product" && missing) params.missing = missing;
      if (search) params.search = search;
      if (onlyDrafts) params.has_draft = true;
      if (onlyConflicts) params.conflict = true;
      const { data } = await api.get(path, { params });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setLoading(false);
  }, [rtype, page, pageSize, bucket, missing, search, onlyDrafts, onlyConflicts]);

  useEffect(() => { load(); }, [load]);

  const loadJobs = useCallback(() => {
    api.get("/bulk/jobs", { params: { page_size: 8 } }).then(({ data }) => setJobs(data.items || [])).catch(() => {});
  }, []);
  useEffect(() => { loadJobs(); const t = setInterval(loadJobs, 3000); return () => clearInterval(t); }, [loadJobs]);

  const guardSwitch = (fn) => () => {
    if (dirty && !window.confirm("You have unsaved draft edits. Discard them?")) return;
    setDrafts({}); fn();
  };

  const setDraftField = (id, field, val) => setDrafts((d) => ({ ...d, [id]: { ...(d[id] || {}), [field]: val } }));
  const draftVal = (row, field) => {
    const key = field === "seo_title" ? "draft_seo_title" : "draft_seo_description";
    if (drafts[row.id] && field in drafts[row.id]) return drafts[row.id][field];
    return row[key] ?? "";
  };

  const saveDrafts = async () => {
    const edits = Object.entries(drafts).map(([id, v]) => ({ id, ...v }));
    if (!edits.length) return;
    try {
      const { data } = await api.post("/bulk/draft-save", { resource_type: rtype, edits });
      toast.success(`Saved ${data.saved} draft(s) — not published to Shopify`);
      setDrafts({}); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const pageIds = items.map((i) => i.id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  const toggleRow = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); setAllFiltered(false); return n; });
  const togglePage = () => setSelected((s) => {
    const n = new Set(s);
    if (allPageSelected) pageIds.forEach((id) => n.delete(id)); else pageIds.forEach((id) => n.add(id));
    setAllFiltered(false); return n;
  });
  const clearSelection = () => { setSelected(new Set()); setAllFiltered(false); };
  const selectionCount = allFiltered ? total : selected.size;

  const selectionBody = () => allFiltered
    ? { resource_type: rtype, all_filtered: true, filter: { bucket, missing, search, has_draft: onlyDrafts, conflict: onlyConflicts, resource_type: rtype } }
    : { resource_type: rtype, ids: Array.from(selected) };

  const runValidate = async () => {
    if (!selectionCount) { toast.error("Select some records first"); return; }
    try {
      const { data } = await api.post("/bulk/validate", selectionBody());
      setValidation(data.summary);
      toast.success(`Validated ${data.summary.total}: ${data.summary.READY} ready, ${data.summary.WARNING} warnings, ${data.summary.ERROR} errors`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const openPreview = async () => {
    if (!selectionCount) { toast.error("Select some records first"); return; }
    try { const { data } = await api.post("/bulk/publish-preview", selectionBody()); setPreview(data); setAllowWarnings(false); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const doPublish = async () => {
    try {
      const { data } = await api.post("/bulk/publish", { ...selectionBody(), allow_warnings: allowWarnings });
      if (data.deduped) toast.info("Identical publish already in progress (deduplicated)");
      else toast.success(`Publish job started for ${data.queued} record(s)`);
      setPreview(null); clearSelection(); loadJobs();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const clearDrafts = async () => {
    if (!selectionCount) return;
    if (!window.confirm(`Clear drafts on ${selectionCount} record(s)?`)) return;
    try { const { data } = await api.post("/bulk/clear-drafts", selectionBody()); toast.success(`Cleared ${data.cleared} draft(s)`); clearSelection(); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const resolveConflict = async (resolution) => {
    try {
      await api.post("/bulk/resolve-conflict", { resource_type: rtype, id: conflictRow.id, resolution });
      toast.success(resolution === "keep_shopify" ? "Kept Shopify value (draft discarded)" : "Draft rebased onto current Shopify value");
      setConflictRow(null); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const jobAction = async (jobId, action) => {
    const map = { rollback: `/bulk/jobs/${jobId}/rollback`, retry: `/bulk/jobs/${jobId}/retry`, cancel: `/bulk/jobs/${jobId}/cancel` };
    if (action === "rollback" && !window.confirm("Roll back this job's published SEO changes?")) return;
    try { const { data } = await api.post(map[action], {}); toast.success(action === "rollback" ? "Rollback job started" : action === "retry" ? `Requeued ${data.requeued ?? 0}` : "Cancelling"); loadJobs(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Bulk SEO Editor</h1>
          <p className="mt-1 text-sm text-muted-foreground">Server-paginated inline editing. Only SEO title &amp; meta description are editable — commerce fields stay locked.</p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-border p-1">
          <button data-testid="bulk-tab-products" onClick={guardSwitch(() => { setRtype("product"); setPage(1); clearSelection(); })}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${rtype === "product" ? "bg-primary/15 text-primary" : "text-muted-foreground"}`}>Products</button>
          <button data-testid="bulk-tab-collections" onClick={guardSwitch(() => { setRtype("collection"); setPage(1); clearSelection(); })}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${rtype === "collection" ? "bg-primary/15 text-primary" : "text-muted-foreground"}`}>Collections</button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card/40 p-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <input data-testid="bulk-search" value={search} placeholder="Search title / handle / ID"
            onChange={(e) => { setPage(1); setSearch(e.target.value); }}
            className="w-64 rounded-md border border-border bg-background py-1.5 pl-7 pr-2 text-sm" />
        </div>
        <select data-testid="bulk-bucket" value={bucket} onChange={(e) => { setPage(1); setBucket(e.target.value); }}
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm">
          {BUCKETS.map((b) => <option key={b} value={b}>{b.replace(/_/g, " ")}</option>)}
        </select>
        {rtype === "product" && (
          <select data-testid="bulk-missing" value={missing} onChange={(e) => { setPage(1); setMissing(e.target.value); }}
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm">
            <option value="">Any SEO state</option>
            <option value="title">Missing title</option>
            <option value="description">Missing meta</option>
            <option value="both">Missing both</option>
          </select>
        )}
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground"><input type="checkbox" checked={onlyDrafts} onChange={(e) => { setPage(1); setOnlyDrafts(e.target.checked); }} /> Draft exists</label>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground"><input type="checkbox" checked={onlyConflicts} onChange={(e) => { setPage(1); setOnlyConflicts(e.target.checked); }} /> Conflicts</label>
        <div className="ml-auto flex items-center gap-2">
          <select data-testid="bulk-page-size" value={pageSize} onChange={(e) => { setPage(1); setPageSize(Number(e.target.value)); }}
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm">
            {PAGE_SIZES.map((s) => <option key={s} value={s}>{s}/page</option>)}
          </select>
          <button onClick={load} className="rounded-md border border-border p-2 hover:bg-accent"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button>
        </div>
      </div>

      {selectionCount > 0 && (
        <div data-testid="bulk-selection-banner" className="flex flex-wrap items-center gap-3 rounded-lg border border-primary/40 bg-primary/10 px-4 py-2.5 text-sm">
          <span className="font-semibold text-primary">
            {allFiltered ? `All ${total.toLocaleString()} records matching this filter selected` : `${selected.size} record(s) on view selected`}
          </span>
          {!allFiltered && total > selected.size && (
            <button data-testid="bulk-select-all-filtered" onClick={() => setAllFiltered(true)} className="underline text-primary/90">
              Select all {total.toLocaleString()} matching this filter
            </button>
          )}
          <button onClick={clearSelection} className="ml-auto inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"><X className="h-3.5 w-3.5" /> Clear</button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {can("edit") && <button data-testid="bulk-save-drafts" disabled={!dirty} onClick={saveDrafts}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-40"><Save className="h-4 w-4" /> Save Drafts{dirty ? ` (${Object.keys(drafts).length})` : ""}</button>}
        <button data-testid="bulk-validate" onClick={runValidate} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm font-medium hover:bg-accent"><CheckCircle2 className="h-4 w-4" /> Validate Selected</button>
        {can("publish") && <button data-testid="bulk-publish" onClick={openPreview} className="inline-flex items-center gap-1.5 rounded-md border border-emerald-600/50 bg-emerald-600/10 px-3 py-2 text-sm font-medium text-emerald-400 hover:bg-emerald-600/20"><Rocket className="h-4 w-4" /> Review &amp; Publish</button>}
        {can("edit") && <button data-testid="bulk-clear-drafts" onClick={clearDrafts} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-accent"><Ban className="h-4 w-4" /> Clear Drafts</button>}
        {validation && <div className="ml-auto flex items-center gap-3 text-xs">
          <span className="text-emerald-400">{validation.READY} Ready</span>
          <span className="text-amber-400">{validation.WARNING} Warnings</span>
          <span className="text-rose-400">{validation.ERROR} Errors</span>
          <span className="text-muted-foreground">{validation.conflicts} conflicts · {validation.title_changes} titles · {validation.meta_changes} metas</span>
        </div>}
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-card/60 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="w-8 px-2 py-2"><input type="checkbox" checked={allPageSelected} onChange={togglePage} data-testid="bulk-select-page" /></th>
              <th className="px-2 py-2">Name <Lock className="inline h-3 w-3 text-muted-foreground" /></th>
              <th className="px-2 py-2">Draft SEO title</th>
              <th className="px-2 py-2">Draft meta description</th>
              <th className="px-2 py-2">Score</th>
              <th className="px-2 py-2">Status</th>
              <th className="px-2 py-2">Draft / Publish</th>
              <th className="px-2 py-2">Conflict</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => {
              const conf = row.conflict_state && row.conflict_state !== "none";
              const tval = draftVal(row, "seo_title");
              const mval = draftVal(row, "meta_description");
              const locallyDirty = !!drafts[row.id];
              return (
                <tr key={row.id} className={`border-t border-border ${selected.has(row.id) ? "bg-primary/5" : ""}`}>
                  <td className="px-2 py-1.5"><input type="checkbox" checked={selected.has(row.id)} onChange={() => toggleRow(row.id)} /></td>
                  <td className="max-w-[200px] px-2 py-1.5">
                    <div className="truncate font-medium" title={row.title}>{row.title}</div>
                    <div className="truncate font-mono text-[10px] text-muted-foreground">{row.handle}</div>
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center gap-1">
                      <input data-testid={`cell-title-${row.id}`} value={tval} disabled={!can("edit")}
                        onChange={(e) => setDraftField(row.id, "seo_title", e.target.value)}
                        placeholder={row.current_seo_title || "— empty —"}
                        className="w-56 rounded border border-border bg-background px-1.5 py-1 text-xs" />
                      <Counter value={tval} min={rules.title_min} max={rules.title_max} />
                    </div>
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center gap-1">
                      <input data-testid={`cell-meta-${row.id}`} value={mval} disabled={!can("edit")}
                        onChange={(e) => setDraftField(row.id, "meta_description", e.target.value)}
                        placeholder={row.current_seo_description || "— empty —"}
                        className="w-72 rounded border border-border bg-background px-1.5 py-1 text-xs" />
                      <Counter value={mval} min={rules.meta_min} max={rules.meta_max} />
                    </div>
                  </td>
                  <td className="px-2 py-1.5 font-mono">{row.seo_score}</td>
                  <td className="px-2 py-1.5"><span className="rounded bg-accent px-1.5 py-0.5 text-[10px]">{(row.status_bucket || "").replace(/_/g, " ")}</span></td>
                  <td className="px-2 py-1.5 text-[10px]">
                    {locallyDirty && <span className="text-amber-500">● unsaved</span>}
                    {!locallyDirty && row.has_draft && <span className="text-sky-400">draft</span>}
                    {!locallyDirty && !row.has_draft && <span className="text-muted-foreground">—</span>}
                    <div className="text-muted-foreground">{row.publication_status}</div>
                  </td>
                  <td className="px-2 py-1.5">
                    {conf ? (
                      <button data-testid={`conflict-${row.id}`} onClick={() => setConflictRow(row)}
                        className="inline-flex items-center gap-1 rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] text-rose-400">
                        <AlertTriangle className="h-3 w-3" /> {CONFLICT_LABEL[row.conflict_state]}
                      </button>
                    ) : <span className="text-[10px] text-muted-foreground">none</span>}
                  </td>
                </tr>
              );
            })}
            {items.length === 0 && !loading && (
              <tr><td colSpan={8} className="py-16 text-center text-muted-foreground">No records match this filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{total.toLocaleString()} records</span>
        <div className="flex items-center gap-2">
          <button disabled={page <= 1} onClick={guardSwitch(() => setPage((p) => p - 1))} className="rounded-md border border-border p-1.5 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /></button>
          <span data-testid="bulk-page-indicator">Page {page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={guardSwitch(() => setPage((p) => p + 1))} className="rounded-md border border-border p-1.5 disabled:opacity-40"><ChevronRight className="h-4 w-4" /></button>
        </div>
      </div>

      <div className="rounded-lg border border-border">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-sm font-semibold"><Table2 className="h-4 w-4" /> Bulk Publish / Rollback Jobs</div>
        <div className="divide-y divide-border">
          {jobs.length === 0 && <div className="px-4 py-6 text-center text-sm text-muted-foreground">No bulk jobs yet.</div>}
          {jobs.map((j) => {
            const c = j.counts || {};
            const running = ["queued", "running", "recovering"].includes(j.status);
            return (
              <div key={j.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm">
                <span className="font-mono text-xs">{j.id}</span>
                <span className={`rounded px-2 py-0.5 text-[10px] ${running ? "bg-sky-500/15 text-sky-400" : j.status === "completed" ? "bg-emerald-500/15 text-emerald-400" : "bg-amber-500/15 text-amber-400"}`}>{j.status}</span>
                <span className="text-xs text-muted-foreground">{j.type === "bulk_rollback" ? "Rollback" : "Publish"} · {c.total || 0} total · {c.verified || 0} verified · {c.failed || 0} failed · {c.conflicted || 0} conflicted · {c.skipped || 0} skipped</span>
                <div className="h-1.5 w-24 overflow-hidden rounded bg-accent"><div className="h-full bg-primary" style={{ width: `${j.progress || 0}%` }} /></div>
                <div className="ml-auto flex items-center gap-1.5">
                  <button onClick={() => api.get(`/bulk/jobs/${j.id}/items`, { params: { page_size: 100 } }).then(({ data }) => setItemsModal({ job: j, items: data.items }))} className="rounded border border-border px-2 py-1 text-xs hover:bg-accent"><Eye className="h-3 w-3" /></button>
                  {can("publish") && j.status === "completed_with_errors" && <button onClick={() => jobAction(j.id, "retry")} className="rounded border border-border px-2 py-1 text-xs hover:bg-accent"><RefreshCw className="inline h-3 w-3" /> Retry</button>}
                  {can("publish") && running && <button onClick={() => jobAction(j.id, "cancel")} className="rounded border border-border px-2 py-1 text-xs text-amber-400 hover:bg-accent">Cancel</button>}
                  {can("rollback") && j.type !== "bulk_rollback" && (j.status === "completed" || j.status === "completed_with_errors") && <button onClick={() => jobAction(j.id, "rollback")} className="rounded border border-border px-2 py-1 text-xs hover:bg-accent"><RotateCcw className="inline h-3 w-3" /> Rollback</button>}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex items-center gap-2 rounded-md bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400"><ShieldCheck className="h-3.5 w-3.5" /> Every publish is verified against Shopify, re-analyzed and audited. Non-SEO fields can never be written.</div>

      {preview && (
        <Modal onClose={() => setPreview(null)} title="Review before publishing">
          <div className="grid grid-cols-3 gap-3 text-center">
            <Stat label="Ready" value={preview.ready} color="text-emerald-400" />
            <Stat label="Warnings" value={preview.warnings} color="text-amber-400" />
            <Stat label="Errors" value={preview.errors} color="text-rose-400" />
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            {preview.with_drafts} drafts in selection · {preview.title_changes} title changes · {preview.meta_changes} meta changes · {preview.conflicts} conflicts.
            Errors and conflicts are never published.
          </p>
          {preview.warnings > 0 && (
            <label className="mt-3 flex items-center gap-2 rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
              <input type="checkbox" checked={allowWarnings} onChange={(e) => setAllowWarnings(e.target.checked)} data-testid="allow-warnings" />
              I acknowledge and want to publish the {preview.warnings} record(s) with warnings too.
            </label>
          )}
          <div className="mt-4 flex justify-end gap-2">
            <button onClick={() => setPreview(null)} className="rounded-md border border-border px-3 py-2 text-sm">Cancel</button>
            <button data-testid="confirm-publish" onClick={doPublish}
              className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white">
              Publish {allowWarnings ? preview.ready + preview.warnings : preview.ready} SEO change(s)
            </button>
          </div>
        </Modal>
      )}

      {conflictRow && (
        <Modal onClose={() => setConflictRow(null)} title="Resolve stale-data conflict">
          <p className="text-sm text-muted-foreground">Shopify SEO changed after this draft was created. Choose how to resolve.</p>
          <div className="mt-3 space-y-2 text-sm">
            <Field label="Shopify current title" value={conflictRow.current_seo_title} />
            <Field label="Your draft title" value={draftVal(conflictRow, "seo_title") || conflictRow.draft_seo_title} />
            <Field label="Draft based on" value={conflictRow.draft_base_title} />
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <button onClick={() => resolveConflict("keep_shopify")} className="rounded-md border border-border px-3 py-2 text-sm">Keep Shopify (discard draft)</button>
            <button onClick={() => resolveConflict("keep_draft")} className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">Keep my draft</button>
          </div>
        </Modal>
      )}

      {itemsModal && (
        <Modal onClose={() => setItemsModal(null)} title={`Job ${itemsModal.job.id} — records`} wide>
          <div className="max-h-[60vh] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="text-left text-muted-foreground"><tr><th className="py-1">Resource</th><th>Status</th><th>Before to After (title)</th><th>Verify</th><th>Retry</th><th>Error</th></tr></thead>
              <tbody>
                {itemsModal.items.map((it) => (
                  <tr key={it.id} className="border-t border-border">
                    <td className="max-w-[150px] truncate py-1">{it.resource_title}</td>
                    <td>{it.status}</td>
                    <td className="max-w-[220px] truncate">{it.before?.title || "empty"} → {it.after?.title || "empty"}</td>
                    <td>{it.verify_result || "—"}</td>
                    <td>{it.retry_count || 0}</td>
                    <td className="max-w-[160px] truncate text-rose-400">{it.last_error || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Modal({ title, children, onClose, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className={`w-full ${wide ? "max-w-3xl" : "max-w-lg"} rounded-xl border border-border bg-card p-5 shadow-xl`} onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between"><h3 className="font-heading text-lg font-semibold">{title}</h3><button onClick={onClose}><XCircle className="h-5 w-5 text-muted-foreground" /></button></div>
        {children}
      </div>
    </div>
  );
}
function Stat({ label, value, color }) {
  return <div className="rounded-lg border border-border p-3"><div className={`font-heading text-2xl font-bold ${color}`}>{value}</div><div className="text-xs text-muted-foreground">{label}</div></div>;
}
function Field({ label, value }) {
  return <div className="rounded-md border border-border bg-background px-3 py-2"><div className="text-[10px] uppercase text-muted-foreground">{label}</div><div className="font-mono text-xs">{value || "— empty —"}</div></div>;
}
