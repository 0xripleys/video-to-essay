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

function dateKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function dateGroupLabel(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function groupVideosByDate(videos: Video[]): { label: string; videos: Video[] }[] {
  const sorted = [...videos].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  const map = new Map<string, Video[]>();
  for (const v of sorted) {
    const key = dateKey(v.created_at);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(v);
  }

  return Array.from(map, ([key, videos]) => ({
    label: dateGroupLabel(videos[0].created_at),
    videos,
  }));
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

function isInProgress(video: Video): boolean {
  return video.status === "processing" || video.status === "pending_download";
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
    const hasInProgress = videos.some(isInProgress);
    if (!hasInProgress) return;

    const interval = setInterval(fetchVideos, 3000);
    return () => clearInterval(interval);
  }, [videos]);

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6 md:px-6 md:py-8">
        <h1 className="text-xl font-bold tracking-tight">Feed</h1>
      </div>
    );
  }

  const groups = groupVideosByDate(videos);

  return (
    <div className="mx-auto max-w-2xl px-4 py-6 md:px-6 md:py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-tight">Feed</h1>
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
          <div className="space-y-6">
            {groups.map((group) => (
              <div key={group.label}>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-stone-400">
                  {group.label}
                </p>
                <div className="space-y-2">
                  {group.videos.map((v) => (
                    <div
                      key={v.id}
                      className={`flex items-center gap-3 rounded-lg border px-3 py-3 md:gap-4 md:px-4 ${
                        isInProgress(v)
                          ? "border-amber-100 bg-amber-50"
                          : "border-stone-200 bg-white"
                      }`}
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
                      <div className="ml-2 flex-shrink-0 md:ml-4">
                        <StatusBadge video={v} />
                      </div>
                    </div>
                  ))}
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
