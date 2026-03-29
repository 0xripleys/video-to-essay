"use client";

import Dashboard from "./components/Dashboard";
import Landing from "./components/Landing";
import { useAuth } from "./components/AppShell";

export default function Home() {
  const auth = useAuth();

  if (auth === "loading") return null;
  if (auth === "unauthenticated") return <Landing />;
  return <Dashboard />;
}
