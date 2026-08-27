import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Settings as SettingsIcon, ShieldCheck, Database, Cpu, RefreshCw, CheckCircle2, XCircle, Lock } from "lucide-react";
import { toast } from "sonner";

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

export default function Settings() {
  const { can } = useAuth();
  const [settings, setSettings] = useState(null);
  const [diag, setDiag] = useState(null);
  const [rules, setRules] = useState(null);
  const [testing, setTesting] = useState(false);

  const load = () => api.get("/settings").then(({ data }) => { setSettings(data); setRules(data.rules); });
  useEffect(() => { load(); api.get("/diagnostics").then(({ data }) => setDiag(data)); }, []);

  const save = async () => {
    try { await api.put("/settings", rules); toast.success("SEO rules saved. Run reanalysis to apply."); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const testShopify = async () => {
    setTesting(true);
    try {
      const { data } = await api.get("/settings/shopify/test");
      let msg = data.message || (data.connected ? "Connected" : "Not connected");
      if (data.missing_scopes && data.missing_scopes.length) msg += ` Missing scopes: ${data.missing_scopes.join(", ")}`;
      toast[data.connected ? "success" : "error"](msg);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setTesting(false); }
  };
  const reanalyze = async () => { try { await api.post("/reanalyze"); toast.success("Reanalysis job started"); } catch { toast.error("Failed"); } };
  const liveSync = async (full) => { try { await api.post(`/shopify/live-sync?full_resync=${full}`); toast.success(full ? "Full re-sync started" : "Live sync started"); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const verifyPublish = async () => {
    try { const { data } = await api.post("/shopify/verify-publish");
      if (data.skipped) toast.info(data.reason);
      else toast.success(`Publish round-trip verified${data.mock ? " (mock)" : ""}: ${data.verified_match ? "value matches Shopify" : "mismatch"}`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  if (!settings || !rules) return <div className="text-muted-foreground">Loading settings…</div>;

  return (
    <div className="max-w-4xl space-y-6">
      <div><h1 className="font-heading text-3xl font-bold tracking-tight">Store & Rule Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">Configure recommended SEO ranges, brand and target market. Tokens are never displayed.</p></div>

      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="mb-4 flex items-center gap-2 font-heading text-lg font-semibold"><ShieldCheck className="h-5 w-5 text-primary" /> Shopify Connection</h2>
        <div className="space-y-2">
          <Row label="Active mode" value={<span className="font-mono uppercase">{settings.shopify.mode}{settings.shopify.mock_mode && settings.shopify.mode === "live" ? " · mock" : ""}</span>} />
          <Row label="Status" ok={settings.shopify.connected} value={settings.shopify.connected ? (settings.shopify.mock_mode ? "Connected (mock)" : "Connected") : "Not connected (demo data)"} />
          <Row label="Store domain" value={settings.shopify.store_domain || "—"} />
          <Row label="API version" value={settings.shopify.api_version} />
          <Row label="Data source" value={<span className="font-mono uppercase">{settings.shopify.data_source}</span>} />
          <Row label="Last sync" value={settings.shopify.last_sync ? new Date(settings.shopify.last_sync).toLocaleString() : "Never"} />
          {settings.shopify.counts && (
            <Row label="Last sync results" value={<span className="font-mono text-xs">{settings.shopify.counts.new}+ new · {settings.shopify.counts.updated} upd · {settings.shopify.counts.unchanged} same · {settings.shopify.counts.deleted} del · {settings.shopify.counts.failed} fail</span>} />
          )}
        </div>
        {can("settings") && (
          <div className="mt-4 flex flex-wrap gap-2">
            <button data-testid="settings-test-shopify-btn" onClick={testShopify} disabled={testing}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
              {testing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} Test Shopify Connection
            </button>
            <button onClick={reanalyze} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
              <RefreshCw className="h-4 w-4" /> Re-run SEO Analysis
            </button>
            {settings.shopify.mode === "live" && (
              <>
                <button data-testid="settings-full-resync-btn" onClick={() => liveSync(true)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
                  <RefreshCw className="h-4 w-4" /> Full Re-sync
                </button>
                <button data-testid="settings-verify-publish-btn" onClick={verifyPublish}
                  className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
                  <ShieldCheck className="h-4 w-4" /> Verify Publish Round-trip
                </button>
              </>
            )}
          </div>
        )}
        {settings.shopify.mode === "demo" && <div className="mt-3 flex items-center gap-2 rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-500"><Lock className="h-3.5 w-3.5" /> DEMO mode active. Seeded data is used and never published to a real store. Set APP_DATA_MODE=live to connect Shopify.</div>}
        {settings.shopify.mode === "live" && settings.shopify.mock_mode && <div className="mt-3 flex items-center gap-2 rounded-md bg-sky-500/10 px-3 py-2 text-xs text-sky-400"><ShieldCheck className="h-3.5 w-3.5" /> LIVE mode using a MOCK Shopify store (no real credentials). Set SHOPIFY_MOCK_MODE=false with real credentials to go live.</div>}
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="mb-4 flex items-center gap-2 font-heading text-lg font-semibold"><SettingsIcon className="h-5 w-5 text-primary" /> SEO Rules</h2>
        <div className="grid grid-cols-2 gap-4">
          {[["title_min", "Title recommended min"], ["title_max", "Title recommended max"],
            ["meta_min", "Meta recommended min"], ["meta_max", "Meta recommended max"]].map(([k, l]) => (
            <div key={k}>
              <label className="mb-1 block text-xs text-muted-foreground">{l}</label>
              <input type="number" data-testid={`settings-${k}`} value={rules[k]} onChange={(e) => setRules({ ...rules, [k]: Number(e.target.value) })}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
            </div>
          ))}
          <div><label className="mb-1 block text-xs text-muted-foreground">Brand name</label>
            <input value={rules.brand} onChange={(e) => setRules({ ...rules, brand: e.target.value })}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" /></div>
          <div><label className="mb-1 block text-xs text-muted-foreground">Target country</label>
            <input value={rules.country} onChange={(e) => setRules({ ...rules, country: e.target.value })}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" /></div>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">Google does not enforce a strict character limit — these are recommended ranges, shown as guidance and warnings only.</p>
        {can("settings") && <button data-testid="settings-save-btn" onClick={save} className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">Save Rules</button>}
      </div>

      {diag && (
        <div className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-4 flex items-center gap-2 font-heading text-lg font-semibold"><Database className="h-5 w-5 text-primary" /> Diagnostics</h2>
          <div className="space-y-2">
            <Row label="Database connected" ok={diag.database_connected} value={diag.database_connected ? "Healthy" : "Down"} />
            <Row label="Worker healthy" ok={diag.worker_healthy} value="Healthy" />
            <Row label="Shopify connected" ok={diag.shopify_connected} value={diag.shopify_connected ? "Yes" : "Demo"} />
            <Row label="AI provider" ok={diag.ai_configured} value={<span className="flex items-center gap-1"><Cpu className="h-3.5 w-3.5" />{diag.ai_configured ? "Configured" : "Unavailable"}</span>} />
            <Row label="Active jobs" value={<span className="font-mono">{diag.active_jobs}</span>} />
          </div>
        </div>
      )}
    </div>
  );
}
