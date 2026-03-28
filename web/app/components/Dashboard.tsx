"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, apiJson } from "../lib/api";

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

const YOUTUBE_URL_RE =
  /^https?:\/\/(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/)[\w-]{11}/;

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
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function fetchVideos() {
    try {
      const data = await apiJson<Video[]>("/api/videos");
      setVideos(data);
    } catch {
      // auth redirect handled by apiJson
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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!YOUTUBE_URL_RE.test(url)) {
      setError("Please enter a valid YouTube URL.");
      return;
    }

    setSubmitting(true);
    try {
      await api("/api/videos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      setUrl("");
      await fetchVideos();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      {/* Submit bar */}
      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          type="url"
          placeholder="Paste YouTube URL..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500"
        />
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-stone-900 px-5 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {submitting ? "..." : "Convert"}
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {/* Video list */}
      <div className="mt-8">
        <p className="text-xs font-medium uppercase tracking-wider text-stone-400">
          Recent Videos
        </p>
        <div className="mt-3 space-y-2">
          {videos.length === 0 && (
            <p className="py-8 text-center text-sm text-stone-400">
              No videos yet. Paste a YouTube URL above or subscribe to a channel.
            </p>
          )}
          {videos.map((v) => (
            <div
              key={v.id}
              className="flex items-center justify-between rounded-lg border border-stone-200 bg-white px-4 py-3"
            >
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
      </div>
    </div>
  );
}
