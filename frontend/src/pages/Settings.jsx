import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
  Settings as SettingsIcon, ShieldCheck, Database, Cpu, RefreshCw, CheckCircle2,
  XCircle, Lock, KeyRound, Sparkles, FileText, Store, Trash2, Eye, EyeOff,
} from "lucide-react";
import { toast } from "sonner";

const PROVIDER_META = {
  openai: { label: "OpenAI", hint: "e.g. gpt-5.4" },
  anthropic: { label: "Anthropic Claude", hint: "e.g. claude-sonnet-4-5" },
  gemini: { label: "Google Gemini", hint: "e.g. gemini-3.1-pro-preview" },
  deepseek: { label: "DeepSeek", hint: "e.g. deepseek-v4-flash / deepseek-v4-pro" },
};

function Row({ label, ok, value }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-border px-3 py-2.5">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="flex items-center gap-1.5 text-sm">
        {ok === true && <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
        {ok === false && <XCircle className="h-4 w-4 text-rose-400" />}
        {value}
      </span>
    </div>
  );
}

function Field({ label, children, hint }) {
  return (
    <div>
      <label className="mb-1 block text-xs text-muted-foreground">{label}</label>
      {children}
      {hint && <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

const inputCls = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary";

/* ---------------- Shopify Connection ---------------- */
function ShopifyTab({ config, refresh, demoPresent, onOpenCleanup }) {
  const s = config.shopify;
  const [form, setForm] = useState({
    domain: s.domain || "", api_version: s.api_version || "2025-01",
    mode: s.mode || "demo", mock_mode: !!s.mock_mode, token: "",
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [confirmLive, setConfirmLive] = useState(false);

  const doSave = async (formToSave) => {
    setSaving(true);
    try {
      const body = { ...formToSave };
      if (!body.token) delete body.token;
      await api.put("/settings/shopify", body);
      toast.success("Shopify configuration saved. Token stored securely (never displayed).");
      setForm((f) => ({ ...f, token: "" }));
      refresh();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); setConfirmLive(false); }
  };

  const onSaveClick = () => {
    if (form.mode === "live" && s.mode !== "live") { setConfirmLive(true); return; }
    doSave(form);
  };

  const testConn = async () => {
    setTesting(true);
    try {
      const { data } = await api.get("/settings/shopify/test");
      let msg = data.message || (data.connected ? "Connected" : "Not connected");
      if (data.missing_scopes?.length) msg += ` Missing scopes: ${data.missing_scopes.join(", ")}`;
      toast[data.connected ? "success" : "error"](msg);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setTesting(false); }
  };

  const syncShopify = async () => {
    try { await api.post(`/shopify/live-sync?full_resync=true`); toast.success("Shopify sync started (read-only ingestion)."); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="mb-4 flex items-center gap-2 font-heading text-lg font-semibold"><ShieldCheck className="h-5 w-5 text-primary" /> Shopify Connection</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Store domain" hint="your-store.myshopify.com">
            <input data-testid="shopify-domain" className={inputCls} value={form.domain}
              onChange={(e) => setForm({ ...form, domain: e.target.value })} placeholder="your-store.myshopify.com" />
          </Field>
          <Field label="Shopify API version">
            <input data-testid="shopify-api-version" className={inputCls} value={form.api_version}
              onChange={(e) => setForm({ ...form, api_version: e.target.value })} placeholder="2025-01" />
          </Field>
          <Field label="Admin API access token (write-only)"
            hint={s.token_configured ? "Admin Token: Configured ✅ — enter a new value only to replace it." : "Admin Token: Not configured"}>
            <div className="relative">
              <input data-testid="shopify-token" type={showToken ? "text" : "password"} className={inputCls + " pr-9"}
                value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })}
                placeholder={s.token_configured ? "•••••••••• (stored)" : "shpat_..."} autoComplete="new-password" />
              <button type="button" onClick={() => setShowToken((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Data mode">
              <select data-testid="shopify-mode" className={inputCls} value={form.mode}
                onChange={(e) => setForm({ ...form, mode: e.target.value })}>
                <option value="demo">DEMO</option>
                <option value="live">LIVE</option>
              </select>
            </Field>
            <Field label="Mock mode">
              <select data-testid="shopify-mock" className={inputCls} value={form.mock_mode ? "on" : "off"}
                onChange={(e) => setForm({ ...form, mock_mode: e.target.value === "on" })}>
                <option value="on">ON</option>
                <option value="off">OFF</option>
              </select>
            </Field>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button data-testid="shopify-save" onClick={onSaveClick} disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50">
            {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />} Save Shopify Configuration
          </button>
          <button data-testid="shopify-test" onClick={testConn} disabled={testing}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
            {testing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} Test Shopify Connection
          </button>
          {s.mode === "live" && (
            <button data-testid="shopify-sync" onClick={syncShopify}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
              <RefreshCw className="h-4 w-4" /> Sync Shopify
            </button>
          )}
        </div>
        {s.config_error && <div data-testid="config-error" className="mt-3 flex items-center gap-2 rounded-md bg-rose-500/10 px-3 py-2 text-xs text-rose-400"><XCircle className="h-3.5 w-3.5" /> {s.config_error}</div>}
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-3 text-sm font-semibold text-muted-foreground">Status</h3>
        <div className="space-y-2">
          <Row label="Active mode" value={<span className="font-mono uppercase">{s.mode}</span>} />
          <Row label="Connection status" ok={s.connected} value={s.connected ? (s.mock_mode ? "Connected (mock)" : "Connected") : "Not connected"} />
          <Row label="Admin token" ok={s.token_configured} value={s.token_configured ? "Configured" : "Not configured"} />
          <Row label="Store domain" value={s.domain || "—"} />
          <Row label="API version" value={s.api_version} />
          <Row label="Mock mode" ok={!s.mock_mode} value={s.mock_mode ? "On (simulated Shopify)" : "Off (real Shopify)"} />
          <Row label="Last successful connection" value={s.last_connection ? new Date(s.last_connection).toLocaleString() : "Never"} />
          <Row label="Last Shopify sync" value={s.last_sync ? new Date(s.last_sync).toLocaleString() : "Never"} />
          <Row label="Demo Data Present" ok={!demoPresent} value={demoPresent ? "Yes" : "No"} />
        </div>
        {demoPresent && (
          <div className="mt-4 rounded-md border border-border p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium">Remove Demo Data</div>
                <div className="text-xs text-muted-foreground">Permanently deletes only DEMO-tagged records (never LIVE data, users or settings).</div>
              </div>
              <button data-testid="remove-demo-data-btn" onClick={onOpenCleanup}
                className="inline-flex items-center gap-1.5 rounded-md border border-rose-600/50 bg-rose-600/10 px-3 py-2 text-sm text-rose-400 hover:bg-rose-600/20">
                <Trash2 className="h-4 w-4" /> Remove Demo Data
              </button>
            </div>
          </div>
        )}
      </div>

      {confirmLive && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setConfirmLive(false)}>
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-heading text-lg font-semibold text-sky-400">Switch to LIVE Shopify data?</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              <li>DEMO records remain isolated and are not touched.</li>
              <li>No automatic SEO mutation occurs — sync is read-only.</li>
              <li>You must explicitly publish SEO later from the editor.</li>
              <li>No demo data is seeded in LIVE mode.</li>
            </ul>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setConfirmLive(false)} className="rounded-md border border-border px-3 py-2 text-sm">Cancel</button>
              <button data-testid="confirm-live" onClick={() => doSave(form)} disabled={saving}
                className="inline-flex items-center gap-1.5 rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
                Switch to LIVE
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- AI Providers ---------------- */
function ProviderCard({ id, data, refresh }) {
  const meta = PROVIDER_META[id];
  const [model, setModel] = useState(data.model || "");
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(!!data.enabled);
  const [busy, setBusy] = useState(false);
  const [test, setTest] = useState(null);

  const save = async () => {
    setBusy(true);
    try {
      const body = { model, enabled };
      if (apiKey) body.api_key = apiKey;
      await api.put(`/settings/ai/${id}`, body);
      toast.success(`${meta.label} saved.`);
      setApiKey(""); refresh();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const doTest = async () => {
    setBusy(true); setTest(null);
    try {
      const { data: r } = await api.get(`/settings/ai/${id}/test`);
      setTest(r);
      toast[r.connected ? "success" : "error"](r.message || (r.connected ? "Connected" : r.status));
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const removeKey = async () => {
    if (!window.confirm(`Remove the ${meta.label} API key? This cannot be undone.`)) return;
    setBusy(true);
    try { await api.delete(`/settings/ai/${id}/key`); toast.success(`${meta.label} key removed.`); refresh(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  return (
    <div data-testid={`provider-${id}`} className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-heading font-semibold"><Cpu className="h-4 w-4 text-primary" /> {meta.label}</h3>
        <span className={`text-xs ${data.key_configured ? "text-emerald-400" : "text-muted-foreground"}`}>
          {data.key_configured ? "API Key: Configured ✅" : "API Key: Not configured"}
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="API key (write-only)" hint={data.key_configured ? "Enter a value only to replace the stored key." : "Stored encrypted; never displayed."}>
          <input data-testid={`provider-${id}-key`} type="password" className={inputCls} value={apiKey}
            onChange={(e) => setApiKey(e.target.value)} placeholder={data.key_configured ? "•••••••••• (stored)" : "Paste API key"} autoComplete="new-password" />
        </Field>
        <Field label="Model" hint={meta.hint}>
          <input data-testid={`provider-${id}-model`} className={inputCls} value={model} onChange={(e) => setModel(e.target.value)} />
        </Field>
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input data-testid={`provider-${id}-enabled`} type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Enabled
      </label>
      {test && <div className={`mt-2 text-xs ${test.connected ? "text-emerald-400" : "text-rose-400"}`}>{test.status}: {test.message}</div>}
      <div className="mt-3 flex flex-wrap gap-2">
        <button data-testid={`provider-${id}-save`} onClick={save} disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50">
          <KeyRound className="h-3.5 w-3.5" /> {data.key_configured ? "Replace / Save" : "Save"}
        </button>
        <button data-testid={`provider-${id}-test`} onClick={doTest} disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent">
          {busy ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />} Test Connection
        </button>
        {data.key_configured && (
          <button data-testid={`provider-${id}-remove`} onClick={removeKey} disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-md border border-rose-600/50 px-3 py-1.5 text-sm text-rose-400 hover:bg-rose-600/10">
            <Trash2 className="h-3.5 w-3.5" /> Remove Key
          </button>
        )}
      </div>
    </div>
  );
}

function AITab({ config, refresh }) {
  const ai = config.ai;
  const [def, setDef] = useState(ai.default_provider);
  const [enabled, setEnabled] = useState(ai.enabled);
  const [limits, setLimits] = useState({
    max_products_per_job: ai.max_products_per_job, daily_limit: ai.daily_limit, max_concurrency: ai.max_concurrency,
  });
  const enabledProviders = Object.entries(ai.providers).filter(([, p]) => p.enabled && p.key_configured).map(([k]) => k);

  const saveGlobal = async () => {
    try {
      await api.put("/settings/ai", { default_provider: def, enabled, ...limits });
      toast.success("AI settings saved."); refresh();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="mb-1 flex items-center gap-2 font-heading text-lg font-semibold"><Sparkles className="h-5 w-5 text-primary" /> AI Providers</h2>
        <p className="mb-4 text-xs text-muted-foreground">API keys are stored encrypted server-side and never displayed. All AI requests originate from the backend. AI creates local drafts only — it can never publish to Shopify.</p>
        <div className="grid gap-4 lg:grid-cols-2">
          {["openai", "anthropic", "gemini", "deepseek"].map((id) => (
            <ProviderCard key={id} id={id} data={ai.providers[id]} refresh={refresh} />
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-3 text-sm font-semibold">AI Usage & Defaults</h3>
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-md border border-border p-3"><div className="text-xs text-muted-foreground">Requests today</div><div className="font-mono text-lg">{config.usage_today.requests}</div></div>
          <div className="rounded-md border border-border p-3"><div className="text-xs text-muted-foreground">Products generated</div><div className="font-mono text-lg">{config.usage_today.products}</div></div>
          <div className="rounded-md border border-border p-3"><div className="text-xs text-muted-foreground">Est. cost today</div><div className="font-mono text-lg">${config.usage_today.estimated_cost}</div></div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Default SEO provider" hint={enabledProviders.length ? "" : "Enable and configure a provider above to use it by default."}>
            <select data-testid="ai-default-provider" className={inputCls} value={def} onChange={(e) => setDef(e.target.value)}>
              {["openai", "anthropic", "gemini", "deepseek"].map((p) => (
                <option key={p} value={p} disabled={!enabledProviders.includes(p)}>{PROVIDER_META[p].label}{enabledProviders.includes(p) ? "" : " (not configured)"}</option>
              ))}
            </select>
          </Field>
          <Field label="AI enabled">
            <select className={inputCls} value={enabled ? "on" : "off"} onChange={(e) => setEnabled(e.target.value === "on")}>
              <option value="on">On</option><option value="off">Off</option>
            </select>
          </Field>
          <Field label="Max products per AI job">
            <input type="number" className={inputCls} value={limits.max_products_per_job} onChange={(e) => setLimits({ ...limits, max_products_per_job: Number(e.target.value) })} />
          </Field>
          <Field label="Daily generation limit">
            <input type="number" className={inputCls} value={limits.daily_limit} onChange={(e) => setLimits({ ...limits, daily_limit: Number(e.target.value) })} />
          </Field>
          <Field label="Max concurrency">
            <input type="number" className={inputCls} value={limits.max_concurrency} onChange={(e) => setLimits({ ...limits, max_concurrency: Number(e.target.value) })} />
          </Field>
        </div>
        <button data-testid="ai-save-global" onClick={saveGlobal} className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">Save AI Settings</button>
      </div>
    </div>
  );
}

/* ---------------- Prompt Manager ---------------- */
const PROMPT_LABELS = { product_seo: "Product SEO Generation", collection_seo: "Collection SEO Generation", quality_review: "SEO Quality Review" };

function PromptEditor({ id, data, reload }) {
  const [text, setText] = useState(data.text);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState(null);

  const save = async () => {
    setBusy(true);
    try { await api.put(`/settings/prompts/${id}`, { text }); toast.success(`${PROMPT_LABELS[id]} saved as a new version.`); reload(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const restore = async () => {
    if (!window.confirm("Restore the recommended default prompt? Your current text will be saved as a prior version.")) return;
    setBusy(true);
    try { await api.post(`/settings/prompts/${id}/restore-default`); toast.success("Default restored."); reload(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const showHistory = async () => {
    try { const { data: r } = await api.get(`/settings/prompts/${id}/history`); setHistory(r.versions); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div data-testid={`prompt-${id}`} className="rounded-xl border border-border bg-card p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-heading font-semibold"><FileText className="h-4 w-4 text-primary" /> {PROMPT_LABELS[id]}</h3>
        <span className="text-xs text-muted-foreground">v{data.active_version} · {data.versions} version(s){data.is_default ? " · default" : ""}</span>
      </div>
      <textarea data-testid={`prompt-${id}-text`} className={inputCls + " min-h-[160px] font-mono text-xs leading-relaxed"} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="mt-3 flex flex-wrap gap-2">
        <button data-testid={`prompt-${id}-save`} onClick={save} disabled={busy} className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50">Save New Version</button>
        <button data-testid={`prompt-${id}-history`} onClick={showHistory} className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent">History</button>
        <button data-testid={`prompt-${id}-restore`} onClick={restore} className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent">Restore Recommended Default</button>
      </div>
      {history && (
        <div className="mt-3 max-h-40 overflow-auto rounded-md border border-border p-2 text-xs">
          {history.map((v) => (
            <div key={v.version} className="flex justify-between border-b border-border/50 py-1 last:border-0">
              <span>v{v.version} {v.active ? "(active)" : ""}</span>
              <span className="text-muted-foreground">{v.updated_by} · {new Date(v.timestamp).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PromptTab({ prompts, reload }) {
  if (!prompts) return <div className="text-muted-foreground">Loading prompts…</div>;
  return (
    <div className="space-y-4">
      <div className="rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-500">
        <Lock className="mr-1 inline h-3.5 w-3.5" /> Prompt text can be customised but can never grant Shopify permissions. AI always remains draft-only and the backend SEO-only allowlist stays authoritative.
      </div>
      {["product_seo", "collection_seo", "quality_review"].map((id) => (
        <PromptEditor key={id} id={id} data={prompts[id]} reload={reload} />
      ))}
    </div>
  );
}

/* ---------------- Store & SEO (rules) ---------------- */
function StoreTab({ rules, setRules, canSave, onSave }) {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <h2 className="mb-4 flex items-center gap-2 font-heading text-lg font-semibold"><SettingsIcon className="h-5 w-5 text-primary" /> SEO Rules, Brand & Market</h2>
      <div className="grid grid-cols-2 gap-4">
        {[["title_min", "Title recommended min"], ["title_max", "Title recommended max"],
          ["meta_min", "Meta recommended min"], ["meta_max", "Meta recommended max"]].map(([k, l]) => (
          <Field key={k} label={l}>
            <input type="number" data-testid={`settings-${k}`} value={rules[k]} onChange={(e) => setRules({ ...rules, [k]: Number(e.target.value) })} className={inputCls} />
          </Field>
        ))}
        <Field label="Brand name"><input value={rules.brand} onChange={(e) => setRules({ ...rules, brand: e.target.value })} className={inputCls} /></Field>
        <Field label="Target country"><input value={rules.country} onChange={(e) => setRules({ ...rules, country: e.target.value })} className={inputCls} /></Field>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">Google does not enforce a strict character limit — these are recommended ranges, shown as guidance and warnings only.</p>
      {canSave && <button data-testid="settings-save-btn" onClick={onSave} className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">Save Rules</button>}
    </div>
  );
}

/* ---------------- Page ---------------- */
export default function Settings() {
  const { can } = useAuth();
  const isAdmin = can("settings");
  const [settings, setSettings] = useState(null);
  const [config, setConfig] = useState(null);
  const [prompts, setPrompts] = useState(null);
  const [diag, setDiag] = useState(null);
  const [rules, setRules] = useState(null);
  const [tab, setTab] = useState("store");
  const [demoInfo, setDemoInfo] = useState(null);
  const [confirmClean, setConfirmClean] = useState(false);
  const [cleaning, setCleaning] = useState(false);

  const loadBase = () => api.get("/settings").then(({ data }) => { setSettings(data); setRules(data.rules); });
  const loadConfig = () => api.get("/settings/config").then(({ data }) => setConfig(data)).catch(() => {});
  const loadPrompts = () => api.get("/settings/prompts").then(({ data }) => setPrompts(data)).catch(() => {});

  useEffect(() => {
    loadBase();
    api.get("/diagnostics").then(({ data }) => setDiag(data)).catch(() => {});
    if (isAdmin) { loadConfig(); loadPrompts(); }
  }, [isAdmin]);

  const refreshAll = () => { loadBase(); if (isAdmin) loadConfig(); };

  const openCleanup = async () => {
    try { const { data } = await api.get("/settings/demo-data"); setDemoInfo(data); setConfirmClean(true); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const removeDemoData = async () => {
    setCleaning(true);
    try {
      const { data } = await api.delete("/settings/demo-data");
      const d = data.deleted;
      toast.success(`Removed ${d.products} demo products, ${d.collections} collections, ${d.audit} audit & ${d.publish_jobs + d.csv_jobs + d.sync_jobs} demo jobs. LIVE preserved: ${data.live_products_preserved}.`);
      setConfirmClean(false); refreshAll();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setCleaning(false); }
  };
  const saveRules = async () => {
    try { await api.put("/settings", rules); toast.success("SEO rules saved. Run reanalysis to apply."); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  if (!settings || !rules) return <div className="text-muted-foreground">Loading settings…</div>;

  const tabs = [
    { id: "store", label: "Store & SEO", icon: Store },
    ...(isAdmin ? [
      { id: "shopify", label: "Shopify Connection", icon: ShieldCheck },
      { id: "ai", label: "AI Providers", icon: Sparkles },
      { id: "prompts", label: "AI Prompt Manager", icon: FileText },
    ] : []),
    { id: "diag", label: "Diagnostics", icon: Database },
  ];

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="font-heading text-3xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">Secure Admin configuration. Secrets are encrypted server-side and never displayed after saving.</p>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-border">
        {tabs.map((t) => (
          <button key={t.id} data-testid={`tab-${t.id}`} onClick={() => setTab(t.id)}
            className={`inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm ${tab === t.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            <t.icon className="h-4 w-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === "store" && <StoreTab rules={rules} setRules={setRules} canSave={isAdmin} onSave={saveRules} />}
      {tab === "shopify" && isAdmin && config && (
        <ShopifyTab config={config} refresh={refreshAll} demoPresent={settings.demo_data_present} onOpenCleanup={openCleanup} />
      )}
      {tab === "ai" && isAdmin && config && <AITab config={config} refresh={refreshAll} />}
      {tab === "prompts" && isAdmin && <PromptTab prompts={prompts} reload={loadPrompts} />}
      {tab === "diag" && diag && (
        <div className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-4 flex items-center gap-2 font-heading text-lg font-semibold"><Database className="h-5 w-5 text-primary" /> Diagnostics</h2>
          <div className="space-y-2">
            <Row label="Database connected" ok={diag.database_connected} value={diag.database_connected ? "Healthy" : "Down"} />
            <Row label="Worker healthy" ok={diag.worker_healthy} value="Healthy" />
            <Row label="Shopify connected" ok={diag.shopify_connected} value={diag.shopify_connected ? "Yes" : "Demo"} />
            <Row label="AI provider" ok={diag.ai_configured} value={<span className="flex items-center gap-1"><Cpu className="h-3.5 w-3.5" />{diag.ai_configured ? "Configured" : "Unavailable"}</span>} />
            <Row label="Active jobs" value={<span className="font-mono">{diag.active_jobs}</span>} />
            {config && <Row label="Secrets encryption" ok={config.secrets_available} value={config.secrets_available ? "Available" : "Unavailable"} />}
          </div>
        </div>
      )}

      {confirmClean && demoInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setConfirmClean(false)}>
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-heading text-lg font-semibold text-rose-400">Remove Demo Data</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              This will permanently remove <b>{demoInfo.counts.products.toLocaleString()} DEMO products</b>, <b>{demoInfo.counts.collections} demo collections</b> and related demo-only
              drafts ({demoInfo.counts.drafts}), audit records ({demoInfo.counts.audit}) and jobs ({demoInfo.counts.publish_jobs + demoInfo.counts.csv_jobs + demoInfo.counts.sync_jobs}).
              LIVE Shopify data, users and settings are preserved.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setConfirmClean(false)} className="rounded-md border border-border px-3 py-2 text-sm">Cancel</button>
              <button data-testid="confirm-remove-demo" onClick={removeDemoData} disabled={cleaning}
                className="inline-flex items-center gap-1.5 rounded-md bg-rose-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
                {cleaning ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />} Permanently remove {demoInfo.counts.products.toLocaleString()} demo products
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
