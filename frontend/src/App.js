import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import AppShell from "@/components/AppShell";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Products from "@/pages/Products";
import ProductEditor from "@/pages/ProductEditor";
import Collections from "@/pages/Collections";
import Jobs from "@/pages/Jobs";
import Audit from "@/pages/Audit";
import Settings from "@/pages/Settings";
import AiWorkspace from "@/pages/AiWorkspace";
import BulkEditor from "@/pages/BulkEditor";
import Csv from "@/pages/Csv";

function Protected({ children }) {
  const { user } = useAuth();
  if (user === null)
    return <div className="flex h-screen items-center justify-center bg-background text-muted-foreground">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" richColors theme="dark" />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Protected><AppShell /></Protected>}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/products" element={<Products />} />
            <Route path="/products/:id" element={<ProductEditor />} />
            <Route path="/collections" element={<Collections />} />
            <Route path="/bulk" element={<BulkEditor />} />
            <Route path="/ai-workspace" element={<AiWorkspace />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/csv" element={<Csv />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
