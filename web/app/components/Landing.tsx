"use client";

import { useState } from "react";
import { proxyImageUrl } from "../lib/api";

export default function Landing() {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{
    videoId: string;
    title: string;
    channelTitle: string;
    thumbnailUrl: string;
  } | null>(null);
  const [resolving, setResolving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setPreview(null);

    const trimmed = url.trim();
    if (!trimmed) return;

    if (!trimmed.includes("youtube.com") && !trimmed.includes("youtu.be")) {
      setError("Please enter a YouTube URL.");
      return;
    }

    const videoIdMatch = trimmed.match(/(?:v=|youtu\.be\/)([\w-]{11})/);
    if (!videoIdMatch) {
      setError("Couldn't find a video at this URL.");
      return;
    }

    setResolving(true);
    const videoId = videoIdMatch[1];

    // Show preview with thumbnail (YouTube thumbnail URLs are predictable)
    setPreview({
      videoId,
      title: "YouTube Video",
      channelTitle: "",
      thumbnailUrl: `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg`,
    });
    setResolving(false);
  }

  return (
    <div className="flex min-h-screen flex-col bg-stone-50">
      {/* Nav */}
      <nav className="flex items-center justify-between px-8 py-5">
        <a href="/" className="text-[15px] font-semibold tracking-tight text-stone-900">
          Surat
        </a>
        <a
          href="/api/auth/login"
          className="text-sm text-stone-500 transition-colors hover:text-stone-900"
        >
          Sign in
        </a>
      </nav>

      {/* Hero */}
      <div className="flex flex-1 flex-col items-center px-8 pt-24">
        <div className="w-full max-w-lg text-center">
          <h1 className="text-3xl font-bold leading-tight tracking-tight text-stone-900">
            Turn YouTube videos into polished transcripts — delivered to your inbox
          </h1>
          <p className="mx-auto mt-4 max-w-md text-[15px] leading-relaxed text-stone-500">
            Paste a link for a one-off, or subscribe to a channel to get every new video automatically.
          </p>

          {/* URL Input */}
          <form onSubmit={handleSubmit} className="mt-6 flex gap-2">
            <input
              type="text"
              placeholder="Paste a YouTube URL..."
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setError("");
                setPreview(null);
              }}
              className="flex-1 rounded-lg border border-stone-300 bg-white px-4 py-2.5 text-sm shadow-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500"
            />
            <button
              type="submit"
              disabled={resolving}
              className="rounded-lg bg-stone-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {resolving ? "..." : "Convert"}
            </button>
          </form>
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

          {/* Video preview + sign-in prompt */}
          {preview && (
            <div className="mt-4 rounded-lg border border-stone-200 bg-white p-4">
              <div className="flex items-center gap-3">
                <img
                  src={proxyImageUrl(preview.thumbnailUrl)}
                  alt={preview.title}
                  className="h-16 w-28 flex-shrink-0 rounded object-cover"
                />
                <div className="min-w-0 flex-1 text-left">
                  <p className="truncate text-sm font-medium text-stone-900">
                    {preview.title}
                  </p>
                  {preview.channelTitle && (
                    <p className="text-xs text-stone-500">{preview.channelTitle}</p>
                  )}
                </div>
              </div>
              <a
                href="/api/auth/login"
                className="mt-3 inline-flex w-full items-center justify-center rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
              >
                Sign in to start converting
              </a>
            </div>
          )}
        </div>

        {/* Side-by-side example */}
        <div className="mt-16 flex w-full max-w-xl items-stretch justify-center gap-5">
          {/* Video card */}
          <div className="flex-1">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-stone-400">
              Video
            </p>
            <div className="overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm">
              <div className="flex aspect-video items-center justify-center bg-gradient-to-br from-stone-100 to-stone-200">
                <svg
                  width="32"
                  height="32"
                  viewBox="0 0 24 24"
                  fill="none"
                  className="text-stone-400"
                >
                  <path
                    d="M8 5.14v13.72a1 1 0 001.5.86l11-6.86a1 1 0 000-1.72l-11-6.86a1 1 0 00-1.5.86z"
                    fill="currentColor"
                    opacity="0.5"
                  />
                </svg>
              </div>
              <div className="p-3">
                <p className="text-xs font-semibold text-stone-800">
                  How Transformers Changed AI
                </p>
                <p className="mt-0.5 text-[10px] text-stone-400">
                  Tech Channel &middot; 245K views
                </p>
              </div>
            </div>
          </div>

          {/* Arrow */}
          <div className="flex flex-shrink-0 items-center pt-6">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              className="text-stone-300"
            >
              <path
                d="M5 12h14M13 6l6 6-6 6"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>

          {/* Transcript card */}
          <div className="flex-1">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-stone-400">
              Transcript
            </p>
            <div className="overflow-hidden rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
              <p
                className="text-sm font-semibold leading-tight text-stone-800"
                style={{ fontFamily: "'Georgia', serif" }}
              >
                How Transformers Changed AI
              </p>
              <div className="mt-2 space-y-1.5">
                <div className="h-1.5 w-full rounded-full bg-stone-100" />
                <div className="h-1.5 w-[88%] rounded-full bg-stone-100" />
              </div>
              <div className="mt-3 h-10 rounded bg-gradient-to-br from-stone-100 to-stone-150 ring-1 ring-stone-200/50" />
              <p
                className="mt-1 text-[8px] italic text-stone-400"
                style={{ fontFamily: "'Georgia', serif" }}
              >
                Figure 1: Architecture diagram
              </p>
              <div className="mt-2 space-y-1.5">
                <div className="h-1.5 w-full rounded-full bg-stone-100" />
                <div className="h-1.5 w-[75%] rounded-full bg-stone-100" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
