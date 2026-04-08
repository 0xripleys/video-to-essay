"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";

type AuthState = "loading" | "authenticated" | "unauthenticated";
type View = "feed" | "channels";

const AuthContext = createContext<AuthState>("loading");
const ViewContext = createContext<{ view: View; setView: (v: View) => void }>({
  view: "feed",
  setView: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function useView() {
  return useContext(ViewContext);
}

function Sidebar() {
  const { view, setView } = useView();
  const router = useRouter();
  const pathname = usePathname();

  const navigate = (v: View) => {
    setView(v);
    if (pathname !== "/") router.push("/");
  };

  return (
    <aside className="hidden md:flex w-52 flex-shrink-0 flex-col border-r border-stone-200 bg-stone-50 px-3 pb-6 pt-4">
      <a href="/" className="mb-6 px-2 text-[15px] font-semibold tracking-tight text-stone-900">
        Scrivi
      </a>

      <nav className="flex flex-1 flex-col gap-0.5">
        <button
          onClick={() => navigate("feed")}
          className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors ${
            view === "feed"
              ? "bg-white font-semibold text-stone-900 shadow-sm ring-1 ring-stone-200"
              : "text-stone-500 hover:bg-stone-100 hover:text-stone-700"
          }`}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <path d="M4 6h16M4 12h16M4 18h7" />
          </svg>
          Feed
        </button>

        <button
          onClick={() => navigate("channels")}
          className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors ${
            view === "channels"
              ? "bg-white font-semibold text-stone-900 shadow-sm ring-1 ring-stone-200"
              : "text-stone-500 hover:bg-stone-100 hover:text-stone-700"
          }`}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <path d="M8 21h8M12 17v4" />
          </svg>
          Channels
        </button>
      </nav>

      <div className="border-t border-stone-200 pt-3">
        <a
          href="/api/auth/logout"
          className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700"
        >
          Sign out
        </a>
      </div>
    </aside>
  );
}

function MobileHeader() {
  const { view, setView } = useView();
  const router = useRouter();
  const pathname = usePathname();

  const navigate = (v: View) => {
    setView(v);
    if (pathname !== "/") router.push("/");
  };

  return (
    <header className="flex md:hidden items-center justify-between border-b border-stone-200 bg-stone-50 px-4 py-3">
      <a href="/" className="text-[15px] font-semibold tracking-tight text-stone-900">
        Scrivi
      </a>
      <nav className="flex items-center gap-1">
        <button
          onClick={() => navigate("feed")}
          className={`rounded-lg px-3 py-1.5 text-[13px] transition-colors ${
            view === "feed"
              ? "bg-white font-semibold text-stone-900 shadow-sm ring-1 ring-stone-200"
              : "text-stone-500"
          }`}
        >
          Feed
        </button>
        <button
          onClick={() => navigate("channels")}
          className={`rounded-lg px-3 py-1.5 text-[13px] transition-colors ${
            view === "channels"
              ? "bg-white font-semibold text-stone-900 shadow-sm ring-1 ring-stone-200"
              : "text-stone-500"
          }`}
        >
          Channels
        </button>
      </nav>
    </header>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<AuthState>("loading");
  const [view, setView] = useState<View>("feed");

  useEffect(() => {
    fetch("/api/auth/me", { credentials: "include" })
      .then((res) => setAuth(res.ok ? "authenticated" : "unauthenticated"))
      .catch(() => setAuth("unauthenticated"));
  }, []);

  return (
    <AuthContext.Provider value={auth}>
      <ViewContext.Provider value={{ view, setView }}>
        {auth === "loading" ? null : auth === "authenticated" ? (
          <div className="flex h-screen flex-col md:flex-row">
            <MobileHeader />
            <Sidebar />
            <main className="flex-1 overflow-y-auto">{children}</main>
          </div>
        ) : (
          <>{children}</>
        )}
      </ViewContext.Provider>
    </AuthContext.Provider>
  );
}
