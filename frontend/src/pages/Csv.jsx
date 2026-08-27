import React, { useEffect, useState, useCallback } from "react";
import { ArrowDownUp, ShieldCheck, Upload, Download, CheckCircle2, AlertTriangle, XCircle, RefreshCw } from "lucide-react";
import { api, formatApiError, API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Csv() {
  const { can } = useAuth();
  const [rtype, setRtype] = useState("product");
  const [exBucket, setExBucket] = useState("all");
  const [exMissing, setExMissing] = useState("");
  const [jobs, setJobs] = useState([]);
  const [preview, setPreview] = useState(null);
  const [rowsTab, setRowsTab] = useState("ERROR");
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);

  const loadJobs = useCallback(() => {
    api.get("/csv/jobs", { params: { page_size: 10 } }).then(({ data }) => setJobs(data.items || [])).catch(() => {});
  }, []);
  useEffect(() => { loadJobs(); const t = setInterval(loadJobs, 3000); return () => clearInterval(t); }, [loadJobs]);

  const doExport = async () => {
    try {
      const filter = { resource_type: rtype, bucket: exBucket };
      if (rtype === "product" && exMissing) filter.missing = exMissing;
      const { data } = await api.post("/csv/export", { resource_type: rtype, filter });
      toast.success(`Export job ${data.job_id} started`); loadJobs();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const download = async (job) => {
    try {
      const res = await api.get(`/csv/download/${job.id}?token=${job.download_token}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a"); a.href = url; a.download = job.filename || "export.csv"; a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) { toast.error("Download failed (export may have expired — regenerate)"); }
  };

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true); setPreview(null);
    try {
      const fd = new FormData();
      fd.append("file", file); fd.append("resource_type", rtype);
      const { data } = await api.post("/csv/import", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setPreview(data);
      loadRows(data.csv_job_id, "ERROR");
      toast.success(`Parsed ${data.counts.total} rows`);
    } catch (err) {
      const d = err.response?.data?.detail;
      if (d && d.code === "CSV_FORBIDDEN_COLUMN") toast.error(`Rejected: forbidden columns (${(d.forbidden_columns || []).join(", ")}) — SEO-only import`);
      else toast.error(formatApiError(typeof d === "object" ? d.message : d));
    }
    setBusy(false); e.target.value = "";
  };

  const loadRows = (cid, sev) => {
    setRowsTab(sev);
    api.get(`/csv/import/${cid}/rows`, { params: { severity: sev, page_size: 50 } })
      .then(({ data }) => setRows(data.items || [])).catch(() => setRows([]));
  };

  const confirmImport = async (includeWarnings) => {
    if (!preview) return;
    if (!window.confirm(`Import ${includeWarnings ? preview.counts.READY + preview.counts.WARNING : preview.counts.READY} row(s) as local SEO drafts? Nothing is published to Shopify.`)) return;
    try {
      await api.post(`/csv/import/${preview.csv_job_id}/confirm`, { include_warnings: includeWarnings });
      toast.success("Import started — drafts are being created. Publish them from the Bulk Editor.");
      setPreview(null); loadJobs();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading text-3xl font-bold tracking-tight">CSV Import / Export</h1>
        <p className="mt-1 text-sm text-muted-foreground">Export filtered records and re-import SEO drafts with a Ready/Warnings/Errors preview. Commerce columns are rejected.</p>
      </div>

      <div className="flex items-center gap-1 rounded-lg border border-border p-1 w-fit">
        <button onClick={() => setRtype("product")} className={`rounded-md px-3 py-1.5 text-sm ${rtype === "product" ? "bg-primary/15 text-primary" : "text-muted-foreground"}`}>Products</button>
        <button onClick={() => setRtype("collection")} className={`rounded-md px-3 py-1.5 text-sm ${rtype === "collection" ? "bg-primary/15 text-primary" : "text-muted-foreground"}`}>Collections</button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Export */}
        <div className="rounded-xl border border-border p-4">
          <div className="flex items-center gap-2 font-heading text-lg font-semibold"><Download className="h-5 w-5" /> Export</div>
          <p className="mt-1 text-sm text-muted-foreground">Includes stable Shopify IDs, current &amp; editable new SEO columns, score and issue codes.</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select value={exBucket} onChange={(e) => setExBucket(e.target.value)} className="rounded-md border border-border bg-background px-2 py-1.5 text-sm">
              {["all", "missing", "critical", "needs_improvement", "good", "optimised"].map((b) => <option key={b} value={b}>{b.replace(/_/g, " ")}</option>)}
            </select>
            {rtype === "product" && (
              <select value={exMissing} onChange={(e) => setExMissing(e.target.value)} className="rounded-md border border-border bg-background px-2 py-1.5 text-sm">
                <option value="">Any SEO state</option><option value="title">Missing title</option><option value="description">Missing meta</option><option value="both">Missing both</option>
              </select>
            )}
            {can("csv") && <button data-testid="csv-export-btn" onClick={doExport} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"><Download className="h-4 w-4" /> Export current filter</button>}
          </div>
        </div>

        {/* Import */}
        <div className="rounded-xl border border-border p-4">
          <div className="flex items-center gap-2 font-heading text-lg font-semibold"><Upload className="h-5 w-5" /> Import</div>
          <p className="mt-1 text-sm text-muted-foreground">Only <code>new_seo_title</code> &amp; <code>new_meta_description</code> are writable. Forbidden columns are rejected.</p>
          {can("csv") ? (
            <label className="mt-3 flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed border-border py-4 text-sm hover:bg-accent">
              <Upload className="h-4 w-4" /> {busy ? "Parsing…" : "Choose CSV file"}
              <input data-testid="csv-file-input" type="file" accept=".csv,text/csv" className="hidden" onChange={onUpload} disabled={busy} />
            </label>
          ) : <div className="mt-3 text-xs text-muted-foreground">You do not have CSV permission.</div>}
        </div>
      </div>

      {/* Import preview */}
      {preview && (
        <div className="rounded-xl border border-border p-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="font-heading text-lg font-semibold">Import preview</div>
            <span className="text-emerald-400 text-sm">{preview.counts.READY} Ready</span>
            <span className="text-amber-400 text-sm">{preview.counts.WARNING} Warnings</span>
            <span className="text-rose-400 text-sm">{preview.counts.ERROR} Errors</span>
            <div className="ml-auto flex gap-2">
              <button onClick={() => confirmImport(false)} disabled={!preview.counts.READY}
                className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40">
                <CheckCircle2 className="h-4 w-4" /> Import {preview.counts.READY} Ready
              </button>
              {preview.counts.WARNING > 0 && <button onClick={() => confirmImport(true)} className="rounded-md border border-amber-600/50 bg-amber-600/10 px-3 py-2 text-sm text-amber-400">Include {preview.counts.WARNING} warnings</button>}
            </div>
          </div>
          <div className="mt-3 flex gap-2 text-xs">
            {["ERROR", "WARNING", "READY"].map((s) => (
              <button key={s} onClick={() => loadRows(preview.csv_job_id, s)}
                className={`rounded px-2 py-1 ${rowsTab === s ? "bg-primary/15 text-primary" : "text-muted-foreground"}`}>{s}</button>
            ))}
          </div>
          <div className="mt-2 max-h-72 overflow-y-auto rounded-md border border-border">
            <table className="w-full text-xs">
              <thead className="text-left text-muted-foreground"><tr><th className="px-2 py-1">Row</th><th>Ref</th><th>New title</th><th>Codes</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-border">
                    <td className="px-2 py-1">{r.row_number}</td>
                    <td className="max-w-[180px] truncate font-mono">{r.shopify_ref}</td>
                    <td className="max-w-[220px] truncate">{r.new_seo_title}</td>
                    <td className="text-rose-400">{(r.codes || []).join(", ")}</td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={4} className="py-6 text-center text-muted-foreground">No {rowsTab.toLowerCase()} rows.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* CSV jobs */}
      <div className="rounded-xl border border-border">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-sm font-semibold"><ArrowDownUp className="h-4 w-4" /> CSV Jobs</div>
        <div className="divide-y divide-border">
          {jobs.length === 0 && <div className="px-4 py-6 text-center text-sm text-muted-foreground">No CSV jobs yet.</div>}
          {jobs.map((j) => (
            <div key={j.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm">
              <span className="font-mono text-xs">{j.id}</span>
              <span className="rounded bg-accent px-2 py-0.5 text-[10px]">{j.kind}</span>
              <span className={`rounded px-2 py-0.5 text-[10px] ${["queued", "running"].includes(j.status) ? "bg-sky-500/15 text-sky-400" : j.status === "completed" ? "bg-emerald-500/15 text-emerald-400" : "bg-amber-500/15 text-amber-400"}`}>{j.status}</span>
              <span className="text-xs text-muted-foreground">{j.filename}{j.counts ? ` · ${j.counts.total ?? ""} rows` : ""}{j.drafts_created ? ` · ${j.drafts_created} drafts` : ""}</span>
              {j.kind === "export" && j.status === "completed" && can("csv") && (
                <button onClick={() => download(j)} className="ml-auto inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-xs hover:bg-accent"><Download className="h-3 w-3" /> Download</button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2 rounded-md bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400"><ShieldCheck className="h-3.5 w-3.5" /> CSV import creates local drafts only — it never publishes and can never write non-SEO fields.</div>
    </div>
  );
}
