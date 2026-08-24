import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, Lock } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { formatApiError } from "@/lib/api";
import { toast } from "sonner";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("msabhadiya007@gmail.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await login(email, password);
      toast.success("Welcome back");
      navigate("/");
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || err.message);
    } finally { setLoading(false); }
  };

  return (
    <div className="dark flex min-h-screen items-center justify-center bg-background p-4 text-foreground">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <ShieldCheck className="h-7 w-7" />
          </div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">UrbanDotted SEO Operations</h1>
          <p className="mt-2 text-sm text-muted-foreground">SEO-only Shopify management. Commerce data stays read-only.</p>
        </div>
        <form onSubmit={submit} className="space-y-4 rounded-xl border border-border bg-card p-6">
          <div>
            <label className="mb-1.5 block text-sm font-medium">Email</label>
            <input data-testid="login-email-input" type="email" value={email}
              onChange={(e) => setEmail(e.target.value)} required
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium">Password</label>
            <input data-testid="login-password-input" type="password" value={password}
              onChange={(e) => setPassword(e.target.value)} required
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
          </div>
          {error && <div data-testid="login-error" className="rounded-md bg-rose-500/10 px-3 py-2 text-sm text-rose-400">{error}</div>}
          <button data-testid="login-submit-btn" type="submit" disabled={loading}
            className="w-full rounded-md bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-60">
            {loading ? "Signing in…" : "Sign in"}
          </button>
          <div className="flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground">
            <Lock className="h-3 w-3" /> Internal admin tool — authorized operators only
          </div>
        </form>
      </div>
    </div>
  );
}
