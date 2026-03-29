"use client";

import { useEffect, useState } from "react";
import { apiJson } from "../lib/api";

interface User {
  id: string;
  email: string;
}

export default function SettingsPage() {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    apiJson<User>("/api/auth/me")
      .then(setUser)
      .catch(() => {});
  }, []);

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="text-xl font-bold tracking-tight">Settings</h1>

      <div className="mt-8 space-y-6">
        <div className="rounded-lg border border-stone-200 bg-white p-6">
          <h2 className="text-sm font-medium text-stone-900">Account</h2>
          <p className="mt-2 text-sm text-stone-500">
            {user ? user.email : "Loading..."}
          </p>
        </div>

        <div className="rounded-lg border border-stone-200 bg-white p-6">
          <h2 className="text-sm font-medium text-stone-900">Sign out</h2>
          <p className="mt-1 text-sm text-stone-500">
            You&apos;ll need to sign in again to access your videos and subscriptions.
          </p>
          <a
            href="/api/auth/logout"
            className="mt-4 inline-block rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50"
          >
            Sign out
          </a>
        </div>
      </div>
    </div>
  );
}
