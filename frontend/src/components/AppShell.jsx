import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, ShoppingBag, FolderTree, Table2, Sparkles, Activity,
  ArrowDownUp, History, Settings as SettingsIcon, ShieldCheck, Moon, Sun,
  LogOut, RefreshCw, Lock,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { toast } from "sonner";

const NAV = [
  { to: "/", label: "SEO Health Command", icon: LayoutDashboard, end: true },
  { to: "/products", label: "Products SEO", icon: ShoppingBag },
  { to: "/collections", label: "Collections SEO", icon: FolderTree },
  { to: "/bulk", label: "Bulk Editor", icon: Table2 },
  { to: "/ai-workspace", label: "AI SEO Engine", icon: Sparkles },
  { to: "/jobs", label: "Job Center", icon: Activity },
  { to: "/csv", label: "CSV Import / Export", icon: ArrowDownUp },
  { to: "/audit", label: "Audit & Rollback", icon: History },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export default function AppShell() {
  const { user, logout, can } = useAuth();
  const navigate = useNavigate();
  const [dark, setDark] = useState(() => localStorage.getItem("ud_theme") !== "light");
  const [sync, setSync] = useState(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("ud_theme", dark ? "dark" : "light");
  }, [dark]);

  const loadSync = () => api.get("/sync/status").then(({ data }) => setSync(data)).catch(() => {});
  useEffect(() => { loadSync(); const t = setInterval(loadSync, 5000); return () => clearInterval(t); }, []);

  const triggerSync = async () => {
    try {
      await api.post("/sync");
      toast.success("Shopify sync started");
      loadSync();
    } catch (e) { toast.error("Could not start sync"); }
  };

  const activeJob = sync?.active_job;
  const lastSync = sync?.sync_state?.last_sync;

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col border-r border-border bg-card/60">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div className="leading-tight">
            <div className="font-heading text-sm font-bold tracking-tight">UrbanDotted</div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">SEO Operations</div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}
              data-testid={`nav-${item.label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent hover:text-foreground"
                }`}>
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border p-3">
          <div className="flex items-start gap-2 rounded-md bg-amber-500/10 p-2.5 text-[11px] text-amber-500">
            <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>SEO-Only Guardrail active. Price, inventory & SKU are read-only locked.</span>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-between gap-4 border-b border-border bg-card/40 px-6 py-3 backdrop-blur-md">
          <div className="flex items-center gap-3 text-sm">
            <span className={`inline-flex h-2 w-2 rounded-full ${sync?.connected ? "bg-emerald-500" : "bg-amber-500"}`} />
            <span className="text-muted-foreground">
              {sync?.connected ? "Shopify connected" : "Demo data source"}
              {sync?.data_source && <span className="ml-1 font-mono text-xs">({sync.data_source})</span>}
            </span>
            {lastSync && <span className="text-xs text-muted-foreground">• Synced {new Date(lastSync).toLocaleTimeString()}</span>}
            {activeJob && (
              <span className="ml-2 inline-flex items-center gap-1.5 rounded-full bg-sky-500/15 px-2.5 py-0.5 text-xs text-sky-400">
                <RefreshCw className="h-3 w-3 animate-spin" /> {activeJob.type} {activeJob.progress}%
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {can("sync") && (
              <button data-testid="header-sync-now-btn" onClick={triggerSync} disabled={!!activeJob}
                className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium hover:bg-accent disabled:opacity-50">
                <RefreshCw className="h-3.5 w-3.5" /> Sync Now
              </button>
            )}
            <button data-testid="theme-toggle-btn" onClick={() => setDark((d) => !d)}
              className="rounded-md border border-border p-2 hover:bg-accent">
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <div className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5">
              <div className="text-right leading-tight">
                <div className="text-xs font-medium">{user?.name}</div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">{user?.role}</div>
              </div>
              <button data-testid="logout-btn" onClick={() => { logout(); navigate("/login"); }}
                className="rounded p-1 text-muted-foreground hover:text-rose-400">
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
