"use client";

import Dashboard from "./components/Dashboard";
import ChannelsPage from "./components/ChannelsPage";
import Landing from "./components/Landing";
import { useAuth, useView } from "./components/AppShell";

export default function Home() {
  const auth = useAuth();
  const { view } = useView();

  if (auth === "loading") return null;
  if (auth === "unauthenticated") return <Landing />;
  if (view === "channels") return <ChannelsPage />;
  return <Dashboard />;
}
