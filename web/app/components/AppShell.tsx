"use client";

import { createContext, useContext, useEffect, useState } from "react";

type AuthState = "loading" | "authenticated" | "unauthenticated";

const AuthContext = createContext<AuthState>("loading");
export function useAuth() {
  return useContext(AuthContext);
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<AuthState>("loading");

  useEffect(() => {
    fetch("/api/auth/me", { credentials: "include" })
      .then((res) => setAuth(res.ok ? "authenticated" : "unauthenticated"))
      .catch(() => setAuth("unauthenticated"));
  }, []);

  return (
    <AuthContext.Provider value={auth}>
      {auth === "loading" ? null : auth === "authenticated" ? (
        <div className="flex min-h-screen flex-col">
          <nav className="flex items-center justify-between border-b border-stone-200 bg-white px-6 py-3">
            <a href="/" className="text-[15px] font-semibold tracking-tight text-stone-900">
              Surat
            </a>
            <a
              href="/api/auth/logout"
              className="text-sm text-stone-500 hover:text-stone-900"
            >
              Sign out
            </a>
          </nav>
          <main className="flex-1 overflow-y-auto">{children}</main>
        </div>
      ) : (
        <>{children}</>
      )}
    </AuthContext.Provider>
  );
}
