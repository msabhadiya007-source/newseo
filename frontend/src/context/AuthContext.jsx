import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = anon, object = user
  const [permissions, setPermissions] = useState([]);

  useEffect(() => {
    const token = localStorage.getItem("ud_token");
    if (!token) { setUser(false); return; }
    api.get("/auth/me")
      .then(({ data }) => { setUser(data.user); setPermissions(data.permissions || []); })
      .catch(() => { localStorage.removeItem("ud_token"); setUser(false); });
  }, []);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("ud_token", data.token);
    setUser(data.user);
    const me = await api.get("/auth/me");
    setPermissions(me.data.permissions || []);
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem("ud_token");
    setUser(false);
    setPermissions([]);
  };

  const can = (perm) => permissions.includes(perm);

  return (
    <AuthContext.Provider value={{ user, permissions, login, logout, can }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
