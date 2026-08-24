import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import ScoreDial from "@/components/ScoreDial";
import SerpPreview from "@/components/SerpPreview";
import { StatusBadge } from "@/components/StatusBadge";
import { lengthStatus, progressPercent, toneColor, toneBar } from "@/lib/seo";
import {
  Lock, ArrowLeft, Save, UploadCloud, Sparkles, RotateCcw, CheckCircle2,
  XCircle, ExternalLink, Copy, Tag,
} from "lucide-react";
import { toast } from "sonner";

const DEFAULT_RULES = { title_min: 50, title_max: 60, meta_min: 140, meta_max: 160 };

function Counter({ len, min, max, testid }) {
  const st = lengthStatus(len, min, max);
  return (
    <div className="mt-1.5 flex items-center justify-between text-xs" data-testid={testid}>
      <span className="font-mono text-muted-foreground">{len} / {max} chars</span>
      <span className={`font-medium ${toneColor[st.tone]}`}>{st.label} • Recommended {min}–{max}</span>
    </div>
  );
}
function Bar({ len, min, max }) {
  const st = lengthStatus(len, min, max);
  return (
    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className={`h-full rounded-full transition-all ${toneBar[st.tone]}`} style={{ width: `${progressPercent(len, max)}%` }} />
    </div>
  );
}

function LockField({ label, value, testid }) {
  return (
    <div data-testid={testid} className="rounded-md border border-border bg-muted/40 px-3 py-2">
      <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-amber-500">
        <Lock className="h-3 w-3" /> {label}
      </div>
      <div className="mt-0.5 text-sm">{value ?? "—"}</div>
    </div>
  );
}

export default function ProductEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { can } = useAuth();
  const [p, setP] = useState(null);
  const [title, setTitle] = useState("");
  const [meta, setMeta] = useState("");
  const [busy, setBusy] = useState(false);
  const [RULES, setRULES] = useState(DEFAULT_RULES);

  useEffect(() => {
    api.get("/settings").then(({ data }) => data?.rules && setRULES({ ...DEFAULT_RULES, ...data.rules })).catch(() => {});
  }, []);

  const load = () => api.get(`/products/${id}`).then(({ data }) => {
    setP(data);
    setTitle(data.draft_seo_title ?? data.current_seo_title ?? "");
    setMeta(data.draft_seo_description ?? data.current_seo_description ?? "");
  });
  useEffect(() => { load(); }, [id]);

  if (!p) return <div className="text-muted-foreground">Loading editor…</div>;

  const saveDraft = async () => {
    setBusy(true);
    try {
      await api.patch(`/products/${id}/seo-draft`, { seo_title: title, meta_description: meta });
      toast.success("Draft saved (not published to Shopify)");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const publish = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/products/${id}/publish-seo`, { seo_title: title, meta_description: meta });
      toast.success(data.verification?.demo ? "Published & verified (demo)" : "Published & verified to Shopify");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const rollback = async () => {
    setBusy(true);
    try { await api.post(`/products/${id}/rollback`); toast.success("Rolled back to previous SEO value"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const aiSuggest = async (field) => {
    setBusy(true);
    toast.loading("Generating with AI…", { id: "ai" });
    try {
      const { data } = await api.post(`/products/${id}/ai-suggest`, { field });
      if (field === "seo_title") setTitle(data.suggestion); else setMeta(data.suggestion);
      toast.success("AI draft applied — review before publishing", { id: "ai" });
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail), { id: "ai" }); }
    finally { setBusy(false); }
  };

  const bd = p.score_breakdown || {};

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to products
        </button>
        <StatusBadge bucket={p.status_bucket} testid="editor-status-badge" />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        {/* LEFT: Read-only Shopify commerce data */}
        <div className="space-y-3 xl:col-span-3">
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="mb-3 flex items-center gap-2 rounded-md bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-500">
              <Lock className="h-3.5 w-3.5" /> LOCKED — Safety Guardrail Active
            </div>
            <div className="mb-3 aspect-square w-full overflow-hidden rounded-lg bg-muted">
              {p.images?.[0]?.src && <img src={p.images[0].src} alt={p.images[0].alt || ""} className="h-full w-full object-cover" />}
            </div>
            <div className="space-y-2">
              <LockField label="Product Title" value={p.title} testid="editor-locked-title" />
              <LockField label="Handle" value={`/${p.handle}`} testid="editor-locked-handle" />
              <div className="grid grid-cols-2 gap-2">
                <LockField label="Price" value={`$${p.price}`} testid="editor-locked-price-badge" />
                <LockField label="Inventory" value={`${p.inventory}`} testid="editor-locked-inventory-badge" />
                <LockField label="SKU" value={p.sku} testid="editor-locked-sku-badge" />
                <LockField label="Status" value={p.status} testid="editor-locked-status" />
              </div>
              <LockField label="Vendor" value={p.vendor} />
              <LockField label="Product Type" value={p.product_type} />
              <div className="rounded-md border border-border bg-muted/40 px-3 py-2">
                <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-amber-500">
                  <Tag className="h-3 w-3" /> Tags
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {(p.tags || []).map((t) => <span key={t} className="rounded bg-muted px-1.5 py-0.5 text-[11px]">{t}</span>)}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* CENTER: Editable SEO + SERP */}
        <div className="space-y-4 xl:col-span-6">
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="mb-1 flex items-center justify-between">
              <label className="text-sm font-semibold">SEO Title</label>
              {can("ai") && <button data-testid="editor-ai-title-btn" onClick={() => aiSuggest("seo_title")} disabled={busy}
                className="inline-flex items-center gap-1 text-xs text-primary hover:underline"><Sparkles className="h-3 w-3" /> AI suggest</button>}
            </div>
            <input data-testid="editor-seo-title-input" value={title} onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
            <Bar len={title.length} min={RULES.title_min} max={RULES.title_max} />
            <Counter len={title.length} min={RULES.title_min} max={RULES.title_max} testid="editor-seo-title-counter" />
          </div>

          <div className="rounded-xl border border-border bg-card p-5">
            <div className="mb-1 flex items-center justify-between">
              <label className="text-sm font-semibold">Meta Description</label>
              {can("ai") && <button data-testid="editor-ai-meta-btn" onClick={() => aiSuggest("meta_description")} disabled={busy}
                className="inline-flex items-center gap-1 text-xs text-primary hover:underline"><Sparkles className="h-3 w-3" /> AI suggest</button>}
            </div>
            <textarea data-testid="editor-seo-meta-textarea" value={meta} onChange={(e) => setMeta(e.target.value)} rows={3}
              className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
            <Bar len={meta.length} min={RULES.meta_min} max={RULES.meta_max} />
            <Counter len={meta.length} min={RULES.meta_min} max={RULES.meta_max} testid="editor-seo-meta-counter" />
            {p.duplicate_description_count > 0 && (
              <div className="mt-2 rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-500">
                This description is also used by {p.duplicate_description_count} other product(s).
              </div>
            )}
          </div>

          <SerpPreview title={title} description={meta} handle={p.handle} testid="editor-serp-preview-card" />

          <div className="flex flex-wrap gap-2">
            <button data-testid="editor-save-draft-btn" onClick={saveDraft} disabled={busy || !can("edit")}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50">
              <Save className="h-4 w-4" /> Save Draft
            </button>
            <button data-testid="editor-publish-shopify-btn" onClick={publish} disabled={busy || !can("publish")}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50">
              <UploadCloud className="h-4 w-4" /> Publish to Shopify
            </button>
            {can("rollback") && (
              <button data-testid="editor-rollback-btn" onClick={rollback} disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-accent">
                <RotateCcw className="h-4 w-4" /> Rollback
              </button>
            )}
            <a href={`https://urbandotted.com/products/${p.handle}`} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-accent">
              <ExternalLink className="h-4 w-4" /> View live
            </a>
          </div>
        </div>

        {/* RIGHT: Explainable score + rules */}
        <div className="space-y-4 xl:col-span-3">
          <div className="rounded-xl border border-border bg-card p-5 text-center">
            <ScoreDial score={p.seo_score} testid="editor-score-dial" />
            <div className="mt-3 text-sm font-semibold">SEO Score {p.seo_score}/100</div>
            <div className="text-xs text-muted-foreground">70% deterministic + 30% AI-assisted</div>
          </div>

          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="mb-3 font-heading text-sm font-semibold">Score Breakdown</h3>
            <div className="space-y-1.5">
              {(bd.positives || []).map((t, i) => (
                <div key={`p${i}`} className="flex items-start gap-2 text-xs text-emerald-400">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {t}
                </div>
              ))}
              {(bd.problems || []).map((t, i) => (
                <div key={`x${i}`} className="flex items-start gap-2 text-xs text-rose-400">
                  <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {t}
                </div>
              ))}
              {(!bd.positives?.length && !bd.problems?.length) && <p className="text-xs text-muted-foreground">No analysis yet.</p>}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="mb-2 font-heading text-sm font-semibold">SEO Rules</h3>
            <div className="space-y-3 text-xs text-muted-foreground">
              <div>
                <div className="font-medium text-foreground">SEO Title</div>
                <ul className="mt-1 list-disc space-y-0.5 pl-4">
                  <li>Recommended ~50–60 characters</li>
                  <li>Clearly identify the product</li>
                  <li>Include natural search language</li>
                  <li>Keep unique, avoid keyword stuffing</li>
                </ul>
              </div>
              <div>
                <div className="font-medium text-foreground">Meta Description</div>
                <ul className="mt-1 list-disc space-y-0.5 pl-4">
                  <li>Recommended ~140–160 characters</li>
                  <li>Accurate purchase context</li>
                  <li>Natural search language, unique</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
