import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Sparkles, Wand2 } from "lucide-react";
import { toast } from "sonner";

export default function AiWorkspace() {
  const { can } = useAuth();
  const [products, setProducts] = useState([]);
  const [selected, setSelected] = useState(null);
  const [field, setField] = useState("meta_description");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/products", { params: { bucket: "missing", page_size: 10 } }).then(({ data }) => {
      setProducts(data.items); if (data.items[0]) setSelected(data.items[0]);
    });
  }, []);

  const generate = async () => {
    if (!selected) return;
    setBusy(true); setResult(""); toast.loading("Generating…", { id: "ai" });
    try {
      const { data } = await api.post(`/products/${selected.id}/ai-suggest`, { field });
      setResult(data.suggestion);
      toast.success("Generated — review, then edit & publish from the product editor", { id: "ai" });
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail), { id: "ai" }); }
    finally { setBusy(false); }
  };

  return (
    <div className="max-w-4xl space-y-5">
      <div><h1 className="font-heading text-3xl font-bold tracking-tight">AI SEO Engine</h1>
        <p className="mt-1 text-sm text-muted-foreground">AI never publishes directly. Flow: Generate → Validate → Score → Human Review → Approve → Publish.</p></div>

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Sample product (missing SEO)</label>
            <select value={selected?.id || ""} onChange={(e) => setSelected(products.find((p) => p.id === e.target.value))}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary">
              {products.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Field</label>
            <select value={field} onChange={(e) => setField(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary">
              <option value="seo_title">SEO Title</option>
              <option value="meta_description">Meta Description</option>
            </select>
          </div>
        </div>
        <button data-testid="ai-workspace-generate-btn" onClick={generate} disabled={busy || !can("ai") || !selected}
          className="mt-4 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50">
          <Wand2 className="h-4 w-4" /> Generate Suggestion
        </button>
        {result && (
          <div className="mt-4 rounded-md border border-sky-500/30 bg-sky-500/10 p-4">
            <div className="mb-1 flex items-center gap-1.5 text-xs text-sky-400"><Sparkles className="h-3.5 w-3.5" /> AI Draft — treated exactly like a human draft (not published)</div>
            <div className="text-sm">{result}</div>
            <div className="mt-1 font-mono text-[11px] text-muted-foreground">{result.length} chars</div>
          </div>
        )}
        <div className="mt-4 rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
          Hallucination guard: the AI is instructed never to invent product claims (waterproof, MagSafe, materials, etc.) unless present in Shopify data. Bulk AI generation with background jobs is planned next.
        </div>
      </div>
    </div>
  );
}
