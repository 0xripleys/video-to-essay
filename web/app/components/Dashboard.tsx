"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, apiJson, proxyImageUrl } from "../lib/api";
import NewDropdown from "./NewDropdown";
import ConvertVideoModal from "./ConvertVideoModal";
import AddChannelModal from "./AddChannelModal";

interface Video {
  id: string;
  youtube_video_id: string;
  youtube_url: string;
  video_title: string | null;
  channel_name: string | null;
  source: string | null;
  status: string;
  error: string | null;
  delivery_sent_at: string | null;
  created_at: string;
}

interface Channel {
  id: string;
  channel_id: string;
  youtube_channel_id: string;
  channel_name: string;
  thumbnail_url: string | null;
  description: string | null;
  active: boolean;
  created_at: string;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function StatusBadge({ video }: { video: Video }) {
  switch (video.status) {
    case "done":
      return (
        <Link
          href={`/reader?id=${video.id}`}
          className="text-xs font-medium text-green-600 hover:text-green-700"
        >
          Ready &rarr;
        </Link>
      );
    case "failed":
      return <span className="text-xs font-medium text-red-500">Failed</span>;
    case "processing":
      return (
        <span className="flex items-center gap-1.5 text-xs font-medium text-amber-600">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-500" />
          Processing
        </span>
      );
    default:
      return (
        <span className="flex items-center gap-1.5 text-xs font-medium text-stone-400">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-stone-300" />
          Queued
        </span>
      );
  }
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
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl text-center">
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

export default function Dashboard() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [convertOpen, setConvertOpen] = useState(false);
  const [channelOpen, setChannelOpen] = useState(false);
  const [unsubTarget, setUnsubTarget] = useState<Channel | null>(null);

  async function fetchVideos() {
    try {
      const data = await apiJson<Video[]>("/api/videos");
      setVideos(data);
    } catch {
      // auth redirect handled
    }
  }

  async function fetchChannels() {
    try {
      const data = await apiJson<Channel[]>("/api/channels");
      setChannels(data);
    } catch {
      // auth redirect handled
    }
  }

  useEffect(() => {
    Promise.all([fetchVideos(), fetchChannels()]).finally(() =>
      setLoading(false),
    );
  }, []);

  // Poll while any videos are in progress
  useEffect(() => {
    const hasInProgress = videos.some(
      (v) => v.status === "processing" || v.status === "pending_download",
    );
    if (!hasInProgress) return;

    const interval = setInterval(fetchVideos, 3000);
    return () => clearInterval(interval);
  }, [videos]);

  function handleUnsubscribed() {
    setUnsubTarget(null);
    fetchChannels();
    fetchVideos();
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="text-xl font-bold tracking-tight">Home</h1>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-tight">Home</h1>
        <NewDropdown
          onConvertVideo={() => setConvertOpen(true)}
          onAddChannel={() => setChannelOpen(true)}
        />
      </div>

      <div className="mt-6 flex gap-8">
        {/* Videos — main column */}
        <div className="min-w-0 flex-[2]">
          {videos.length === 0 ? (
            <div className="flex flex-col items-center py-24">
              <p className="text-sm font-medium text-stone-700">
                No videos yet
              </p>
              <p className="mt-1 text-sm text-stone-400">
                Convert a video or subscribe to a channel to get started.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {videos.map((v) => (
                <div
                  key={v.id}
                  className="flex items-center gap-4 rounded-lg border border-stone-200 bg-white px-4 py-3"
                >
                  <img
                    src={proxyImageUrl(
                      `https://i.ytimg.com/vi/${v.youtube_video_id}/mqdefault.jpg`,
                    )}
                    alt=""
                    className="h-12 w-20 flex-shrink-0 rounded object-cover"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-stone-900">
                      {v.video_title || v.youtube_url}
                    </p>
                    <p className="text-xs text-stone-400">
                      {v.channel_name ||
                        (v.source === "one_off" ? "One-off" : "")}
                      {v.channel_name || v.source ? " \u00b7 " : ""}
                      {relativeTime(v.created_at)}
                    </p>
                  </div>
                  <div className="ml-4 flex-shrink-0">
                    <StatusBadge video={v} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Channels — sidebar */}
        <div className="w-56 flex-shrink-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-stone-400">
            Channels
          </p>
          {channels.length === 0 ? (
            <div className="mt-3">
              <p className="text-sm text-stone-500">No channels yet</p>
              <p className="mt-0.5 text-xs text-stone-400">
                Use + New to subscribe to a channel.
              </p>
            </div>
          ) : (
            <div className="mt-3 space-y-1">
              {channels.map((ch) => (
                <div
                  key={ch.id}
                  className="group flex items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-stone-50"
                >
                  {ch.thumbnail_url ? (
                    <img
                      src={proxyImageUrl(ch.thumbnail_url)}
                      alt={ch.channel_name}
                      className="h-7 w-7 flex-shrink-0 rounded-full object-cover"
                    />
                  ) : (
                    <div className="h-7 w-7 flex-shrink-0 rounded-full bg-stone-200" />
                  )}
                  <span className="min-w-0 flex-1 truncate text-sm text-stone-700">
                    {ch.channel_name}
                  </span>
                  <button
                    onClick={() => setUnsubTarget(ch)}
                    className="flex-shrink-0 text-stone-300 opacity-0 transition-opacity hover:text-stone-500 group-hover:opacity-100"
                    title={`Unsubscribe from ${ch.channel_name}`}
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 14 14"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    >
                      <path d="M4 4l6 6M10 4l-6 6" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <ConvertVideoModal
        open={convertOpen}
        onClose={() => setConvertOpen(false)}
        onConverted={() => fetchVideos()}
      />
      <AddChannelModal
        open={channelOpen}
        onClose={() => setChannelOpen(false)}
        onSubscribed={() => {
          fetchVideos();
          fetchChannels();
        }}
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
