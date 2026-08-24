import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { StatusBadge } from "@/components/StatusBadge";
import SerpPreview from "@/components/SerpPreview";
import { scoreColor, lengthStatus, toneColor } from "@/lib/seo";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FolderTree, Lock, Save, UploadCloud } from "lucide-react";
import { toast } from "sonner";

const R = { title_min: 50, title_max: 60, meta_min: 140, meta_max: 160 };

export default function Collections() {
  const { can } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [edit, setEdit] = useState(null);
  const [title, setTitle] = useState("");
  const [meta, setMeta] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => { setLoading(true); api.get("/collections").then(({ data }) => setItems(data.items)).finally(() => setLoading(false)); };
  useEffect(() => { load(); }, []);

  const open = (c) => { setEdit(c); setTitle(c.current_seo_title || ""); setMeta(c.current_seo_description || ""); };

  const publish = async () => {
    setBusy(true);
    try {
      await api.post(`/collections/${edit.id}/publish-seo`, { seo_title: title, meta_description: meta });
      toast.success("Collection SEO published"); setEdit(null); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const saveDraft = async () => {
    setBusy(true);
    try { await api.patch(`/collections/${edit.id}/seo-draft`, { seo_title: title, meta_description: meta }); toast.success("Draft saved"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading text-3xl font-bold tracking-tight">Collections SEO</h1>
        <p className="mt-1 text-sm text-muted-foreground">Independent SEO records for store collections. Same SEO-only write rules apply.</p>
      </div>

      <div className="overflow-hidden rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead className="bg-card text-left text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
            <tr><th className="px-4 py-3">Collection</th><th className="px-4 py-3">SEO Title</th><th className="px-4 py-3 text-center">Score</th><th className="px-4 py-3">Status</th></tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading && <tr><td colSpan={4} className="px-4 py-10 text-center text-muted-foreground">Loading…</td></tr>}
            {!loading && items.length === 0 && <tr><td colSpan={4} className="px-4 py-16 text-center text-muted-foreground"><FolderTree className="mx-auto mb-3 h-8 w-8" />No collections synced.</td></tr>}
            {!loading && items.map((c) => (
              <tr key={c.id} data-testid="collections-table-row" onClick={() => open(c)} className="cursor-pointer bg-background hover:bg-accent/50">
                <td className="px-4 py-3">
                  <div className="font-medium">{c.title}</div>
                  <div className="flex items-center gap-1 text-[11px] text-muted-foreground"><Lock className="h-2.5 w-2.5" />/{c.handle}</div>
                </td>
                <td className="max-w-[320px] px-4 py-3"><div className="truncate text-muted-foreground">{c.current_seo_title || <span className="text-rose-400">— missing —</span>}</div></td>
                <td className="px-4 py-3 text-center"><span className="font-mono font-bold" style={{ color: scoreColor(c.seo_score) }}>{c.seo_score}</span></td>
                <td className="px-4 py-3"><StatusBadge bucket={c.status_bucket} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{edit?.title}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-semibold">SEO Title</label>
              <input data-testid="collection-seo-title-input" value={title} onChange={(e) => setTitle(e.target.value)}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
              <div className="mt-1 flex justify-between text-xs"><span className="font-mono text-muted-foreground">{title.length}/{R.title_max}</span>
                <span className={toneColor[lengthStatus(title.length, R.title_min, R.title_max).tone]}>{lengthStatus(title.length, R.title_min, R.title_max).label}</span></div>
            </div>
            <div>
              <label className="text-sm font-semibold">Meta Description</label>
              <textarea data-testid="collection-seo-meta-input" value={meta} onChange={(e) => setMeta(e.target.value)} rows={3}
                className="mt-1 w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
              <div className="mt-1 flex justify-between text-xs"><span className="font-mono text-muted-foreground">{meta.length}/{R.meta_max}</span>
                <span className={toneColor[lengthStatus(meta.length, R.meta_min, R.meta_max).tone]}>{lengthStatus(meta.length, R.meta_min, R.meta_max).label}</span></div>
            </div>
            <SerpPreview title={title} description={meta} handle={edit?.handle} />
            <div className="flex justify-end gap-2">
              <button onClick={saveDraft} disabled={busy || !can("edit")} className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm hover:bg-accent disabled:opacity-50"><Save className="h-4 w-4" /> Save Draft</button>
              <button data-testid="collection-publish-btn" onClick={publish} disabled={busy || !can("publish")} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"><UploadCloud className="h-4 w-4" /> Publish</button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
