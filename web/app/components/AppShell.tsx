"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";

type AuthState = "loading" | "authenticated" | "unauthenticated";

const AuthContext = createContext<AuthState>("loading");
export function useAuth() {
  return useContext(AuthContext);
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [auth, setAuth] = useState<AuthState>("loading");

  useEffect(() => {
    fetch("/api/auth/me", { credentials: "include" })
      .then((res) => setAuth(res.ok ? "authenticated" : "unauthenticated"))
      .catch(() => setAuth("unauthenticated"));
  }, []);

  return (
    <AuthContext.Provider value={auth}>
      {auth === "loading" ? null : auth === "authenticated" && pathname !== "/login" ? (
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 overflow-y-auto">{children}</main>
        </div>
      ) : (
        <>{children}</>
      )}
    </AuthContext.Provider>
  );
}
