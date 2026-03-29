"use client";

import { useEffect, useState } from "react";
import { api, apiJson } from "../lib/api";
import AddChannelModal from "../components/AddChannelModal";

interface Subscription {
  id: string;
  channel_id: string;
  channel_name: string;
  youtube_channel_id: string;
  thumbnail_url: string | null;
  description: string | null;
  poll_interval_hours: number;
  active: number;
  created_at: string;
}

export default function SubscriptionsPage() {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);

  async function fetchSubs() {
    try {
      const data = await apiJson<Subscription[]>("/api/channels");
      setSubs(data);
    } catch {
      // auth redirect handled
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchSubs();
  }, []);

  async function handleUnsubscribe(subId: string) {
    try {
      await api(`/api/subscriptions/${subId}`, { method: "DELETE" });
      await fetchSubs();
    } catch {
      // ignore
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <h1 className="text-xl font-bold tracking-tight">Subscriptions</h1>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      {subs.length > 0 ? (
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight">Subscriptions</h1>
          <button
            onClick={() => setModalOpen(true)}
            className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
          >
            + Add channel
          </button>
        </div>
      ) : (
        <h1 className="text-xl font-bold tracking-tight">Subscriptions</h1>
      )}

      {subs.length === 0 ? (
        <div className="flex flex-col items-center py-24">
          <p className="text-sm font-medium text-stone-700">
            You haven&apos;t added any channels yet
          </p>
          <p className="mt-1 text-sm text-stone-400">
            Add a YouTube channel to get started.
          </p>
          <button
            onClick={() => setModalOpen(true)}
            className="mt-4 rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
          >
            + Add channel
          </button>
        </div>
      ) : (
        <div className="mt-6 space-y-3">
          {subs.map((sub) => (
            <div
              key={sub.id}
              className="flex items-start gap-4 rounded-lg border border-stone-200 bg-white px-4 py-3"
            >
              {sub.thumbnail_url && (
                <img
                  src={sub.thumbnail_url}
                  alt={sub.channel_name}
                  className="h-10 w-10 flex-shrink-0 rounded-full object-cover"
                />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-stone-900">
                  {sub.channel_name}
                </p>
                {sub.description && (
                  <p className="mt-0.5 line-clamp-1 text-xs text-stone-500">
                    {sub.description}
                  </p>
                )}
              </div>
              <button
                onClick={() => handleUnsubscribe(sub.id)}
                className="ml-4 flex-shrink-0 text-xs text-stone-400 hover:text-red-500"
              >
                Unsubscribe
              </button>
            </div>
          ))}
        </div>
      )}

      <AddChannelModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubscribed={() => fetchSubs()}
      />
    </div>
  );
}
