"use client";

import { useEffect, useState } from "react";
import { api, apiJson } from "../lib/api";

interface Subscription {
  id: string;
  channel_id: string;
  channel_name: string;
  youtube_channel_id: string;
  poll_interval_hours: number;
  active: number;
  created_at: string;
}

const INTERVAL_OPTIONS = [1, 2, 4, 8, 12, 24];

export default function SubscriptionsPage() {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function fetchSubs() {
    try {
      const data = await apiJson<Subscription[]>("/api/channels");
      setSubs(data);
    } catch {
      // auth redirect handled
    }
  }

  useEffect(() => {
    fetchSubs();
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!url.includes("youtube.com")) {
      setError("Please enter a YouTube channel URL.");
      return;
    }
    setSubmitting(true);
    try {
      await api("/api/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      setUrl("");
      await fetchSubs();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to subscribe.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUnsubscribe(subId: string) {
    try {
      await api(`/api/subscriptions/${subId}`, { method: "DELETE" });
      await fetchSubs();
    } catch {
      // ignore
    }
  }

  async function handleIntervalChange(subId: string, hours: number) {
    try {
      await api(`/api/subscriptions/${subId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ poll_interval_hours: hours }),
      });
      await fetchSubs();
    } catch {
      // ignore
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="text-xl font-bold tracking-tight">Subscriptions</h1>
      <p className="mt-1 text-sm text-stone-500">
        Track YouTube channels and get essays for every new video.
      </p>

      {/* Add channel */}
      <form onSubmit={handleAdd} className="mt-6 flex gap-3">
        <input
          type="url"
          placeholder="Paste YouTube channel URL..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500"
        />
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "..." : "Subscribe"}
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {/* Channel list */}
      <div className="mt-8 space-y-3">
        {subs.length === 0 && (
          <p className="py-8 text-center text-sm text-stone-400">
            No subscriptions yet. Paste a YouTube channel URL above.
          </p>
        )}
        {subs.map((sub) => (
          <div
            key={sub.id}
            className="flex items-center justify-between rounded-lg border border-stone-200 bg-white px-4 py-3"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-stone-900">
                {sub.channel_name}
              </p>
              <p className="text-xs text-stone-400">
                Check every{" "}
                <select
                  value={sub.poll_interval_hours}
                  onChange={(e) =>
                    handleIntervalChange(sub.id, Number(e.target.value))
                  }
                  className="rounded border border-stone-200 bg-stone-50 px-1 py-0.5 text-xs"
                >
                  {INTERVAL_OPTIONS.map((h) => (
                    <option key={h} value={h}>
                      {h === 1 ? "1 hour" : `${h} hours`}
                    </option>
                  ))}
                </select>
              </p>
            </div>
            <button
              onClick={() => handleUnsubscribe(sub.id)}
              className="ml-4 text-xs text-stone-400 hover:text-red-500"
            >
              Unsubscribe
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
