"use client";

import { useEffect, useState } from "react";
import { api, apiJson, proxyImageUrl } from "../lib/api";
import AddChannelModal from "./AddChannelModal";

interface Channel {
  id: string;
  channel_id: string;
  youtube_channel_id: string;
  channel_name: string;
  thumbnail_url: string | null;
  description: string | null;
  video_count: number;
  active: boolean;
  created_at: string;
}

function subscriptionAge(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return "just now";
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

function UnsubscribeModal({
  channel,
  onClose,
  onConfirm,
}: {
  channel: Channel;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const [unsubscribing, setUnsubscribing] = useState(false);

  async function handleUnsubscribe() {
    setUnsubscribing(true);
    try {
      const res = await api(`/api/subscriptions/${channel.id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        onConfirm();
      }
    } catch {
      // ignore
    } finally {
      setUnsubscribing(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-[15vh]"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-sm rounded-xl bg-white p-6 text-center shadow-xl">
        {channel.thumbnail_url && (
          <img
            src={proxyImageUrl(channel.thumbnail_url)}
            alt={channel.channel_name}
            className="mx-auto h-12 w-12 rounded-full object-cover"
          />
        )}
        <p className="mt-3 text-sm font-semibold text-stone-900">
          Unsubscribe from {channel.channel_name}?
        </p>
        <p className="mt-1 text-xs text-stone-400">
          You&apos;ll stop receiving new videos from this channel.
        </p>
        <div className="mt-5 flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 rounded-lg border border-stone-200 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
          >
            Cancel
          </button>
          <button
            onClick={handleUnsubscribe}
            disabled={unsubscribing}
            className="flex-1 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {unsubscribing ? "Removing..." : "Unsubscribe"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ChannelsPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [unsubTarget, setUnsubTarget] = useState<Channel | null>(null);

  async function fetchChannels() {
    try {
      const data = await apiJson<Channel[]>("/api/channels");
      setChannels(data);
    } catch {
      // auth redirect handled
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchChannels();
  }, []);

  function handleUnsubscribed() {
    setUnsubTarget(null);
    fetchChannels();
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-8">
        <h1 className="text-xl font-bold tracking-tight">Channels</h1>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-tight">Channels</h1>
        <button
          onClick={() => setAddOpen(true)}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
        >
          + Add channel
        </button>
      </div>

      <div className="mt-6">
        {channels.length === 0 ? (
          <div className="flex flex-col items-center py-24">
            <p className="text-sm font-medium text-stone-700">
              No channels yet
            </p>
            <p className="mt-1 text-sm text-stone-400">
              Subscribe to YouTube channels to automatically receive new videos
              as essays.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {channels.map((ch) => (
              <div
                key={ch.id}
                className="flex items-center gap-4 rounded-lg border border-stone-200 bg-white px-4 py-3"
              >
                {ch.thumbnail_url ? (
                  <img
                    src={proxyImageUrl(ch.thumbnail_url)}
                    alt={ch.channel_name}
                    className="h-9 w-9 flex-shrink-0 rounded-full object-cover"
                  />
                ) : (
                  <div className="h-9 w-9 flex-shrink-0 rounded-full bg-stone-200" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-stone-900">
                    {ch.channel_name}
                  </p>
                  <p className="text-xs text-stone-400">
                    {ch.video_count} {ch.video_count === 1 ? "video" : "videos"}{" "}
                    &middot; Subscribed {subscriptionAge(ch.created_at)}
                  </p>
                </div>
                <button
                  onClick={() => setUnsubTarget(ch)}
                  className="flex-shrink-0 rounded-lg border border-stone-200 px-3 py-1.5 text-xs text-stone-500 transition-colors hover:border-stone-300 hover:text-stone-700"
                >
                  Unsubscribe
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <AddChannelModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onSubscribed={() => fetchChannels()}
      />
      {unsubTarget && (
        <UnsubscribeModal
          channel={unsubTarget}
          onClose={() => setUnsubTarget(null)}
          onConfirm={handleUnsubscribed}
        />
      )}
    </div>
  );
}
