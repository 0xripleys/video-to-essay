"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiJson, proxyImageUrl } from "../lib/api";
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

export default function Dashboard() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [convertOpen, setConvertOpen] = useState(false);
  const [channelOpen, setChannelOpen] = useState(false);

  async function fetchVideos() {
    try {
      const data = await apiJson<Video[]>("/api/videos");
      setVideos(data);
    } catch {
      // auth redirect handled
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchVideos();
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

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-8">
        <h1 className="text-xl font-bold tracking-tight">Home</h1>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-tight">Home</h1>
        <NewDropdown
          onConvertVideo={() => setConvertOpen(true)}
          onAddChannel={() => setChannelOpen(true)}
        />
      </div>

      <div className="mt-6">
        {videos.length === 0 ? (
          <div className="flex flex-col items-center py-24">
            <p className="text-sm font-medium text-stone-700">No videos yet</p>
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
                  src={proxyImageUrl(`https://i.ytimg.com/vi/${v.youtube_video_id}/mqdefault.jpg`)}
                  alt=""
                  className="h-12 w-20 flex-shrink-0 rounded object-cover"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-stone-900">
                    {v.video_title || v.youtube_url}
                  </p>
                  <p className="text-xs text-stone-400">
                    {v.channel_name || (v.source === "one_off" ? "One-off" : "")}
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

      <ConvertVideoModal
        open={convertOpen}
        onClose={() => setConvertOpen(false)}
        onConverted={() => fetchVideos()}
      />
      <AddChannelModal
        open={channelOpen}
        onClose={() => setChannelOpen(false)}
        onSubscribed={() => fetchVideos()}
      />
    </div>
  );
}
