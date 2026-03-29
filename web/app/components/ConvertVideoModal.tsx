"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiJson, proxyImageUrl } from "../lib/api";

interface VideoResult {
  videoId: string;
  title: string;
  channelTitle: string;
  thumbnailUrl: string;
  viewCount?: string;
  publishedAt?: string;
}

function formatViews(count: string | undefined): string {
  const n = parseInt(count ?? "0", 10);
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M views`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}K views`;
  return `${n} views`;
}

export default function ConvertVideoModal({
  open,
  onClose,
  onConverted,
}: {
  open: boolean;
  onClose: () => void;
  onConverted: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<VideoResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [converting, setConverting] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<VideoResult | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setError("");
      setSelected(null);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  const isUrl = (text: string) =>
    text.includes("youtube.com") || text.includes("youtu.be");

  const handleInputChange = useCallback((value: string) => {
    setQuery(value);
    setError("");
    setResults([]);

    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = value.trim();
    if (!trimmed) return;

    if (isUrl(trimmed)) return;

    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await apiJson<VideoResult[]>(
          `/api/videos/search?q=${encodeURIComponent(trimmed)}`,
        );
        setResults(data);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
  }, []);

  const handleKeyDown = async (e: React.KeyboardEvent) => {
    if (e.key !== "Enter") return;
    const trimmed = query.trim();
    if (!trimmed || !isUrl(trimmed)) return;

    e.preventDefault();
    setResolving(true);
    setError("");

    // Extract video ID from URL and construct a search to get metadata
    const videoIdMatch = trimmed.match(/(?:v=|youtu\.be\/)([\w-]{11})/);
    if (!videoIdMatch) {
      setError("Couldn't find a video at this URL");
      setResolving(false);
      return;
    }

    // Use the video ID to get metadata directly
    try {
      const data = await apiJson<VideoResult[]>(
        `/api/videos/search?q=${encodeURIComponent(videoIdMatch[1])}`,
      );
      // Find the exact video in results, or use first result
      const match = data.find((v) => v.videoId === videoIdMatch[1]) ?? data[0];
      if (match) {
        setSelected(match);
      } else {
        // Even without metadata, we can still convert — create a minimal result
        setSelected({
          videoId: videoIdMatch[1],
          title: "YouTube Video",
          channelTitle: "",
          thumbnailUrl: `https://i.ytimg.com/vi/${videoIdMatch[1]}/mqdefault.jpg`,
        });
      }
    } catch {
      // Fallback: still allow conversion with minimal info
      setSelected({
        videoId: videoIdMatch[1],
        title: "YouTube Video",
        channelTitle: "",
        thumbnailUrl: `https://i.ytimg.com/vi/${videoIdMatch[1]}/mqdefault.jpg`,
      });
    } finally {
      setResolving(false);
    }
  };

  const handleSelectResult = (result: VideoResult) => {
    setSelected(result);
    setResults([]);
  };

  const handleBack = () => {
    setSelected(null);
    setError("");
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  const handleConvert = async () => {
    if (!selected) return;
    setConverting(true);
    setError("");
    try {
      const url = `https://www.youtube.com/watch?v=${selected.videoId}`;
      const res = await api("/api/videos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail || "Failed to start conversion");
      } else {
        onConverted();
        onClose();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setConverting(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-[15vh]"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
        {selected ? (
          <div className="p-6 text-center">
            {selected.thumbnailUrl && (
              <img
                src={proxyImageUrl(selected.thumbnailUrl)}
                alt={selected.title}
                className="mx-auto h-32 w-56 rounded-lg object-cover"
              />
            )}
            <p className="mt-3 text-base font-semibold text-stone-900">
              {selected.title}
            </p>
            {selected.channelTitle && (
              <p className="mt-0.5 text-xs text-stone-500">
                {selected.channelTitle}
                {selected.viewCount ? ` · ${formatViews(selected.viewCount)}` : ""}
              </p>
            )}
            {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
            <div className="mt-5 flex gap-2">
              <button
                onClick={handleBack}
                className="flex-1 rounded-lg border border-stone-200 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
              >
                Back
              </button>
              <button
                onClick={handleConvert}
                disabled={converting}
                className="flex-1 rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
              >
                {converting ? "Converting..." : "Convert"}
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="p-5 pb-0">
              <h2 className="text-base font-semibold text-stone-900">
                Convert a video
              </h2>
              <p className="mt-0.5 text-xs text-stone-500">
                Search for a video or paste a YouTube URL
              </p>
              <input
                ref={inputRef}
                type="text"
                placeholder="Search or paste URL..."
                value={query}
                onChange={(e) => handleInputChange(e.target.value)}
                onKeyDown={handleKeyDown}
                className="mt-3 w-full rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-sm shadow-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500"
              />
              {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
              {resolving && (
                <p className="mt-2 text-xs text-stone-400">Resolving video...</p>
              )}
            </div>

            <div className="mt-1">
              {searching && (
                <p className="px-5 py-3 text-xs text-stone-400">Searching...</p>
              )}
              {!searching && results.length === 0 && query.trim() && !isUrl(query) && (
                <p className="px-5 py-3 text-xs text-stone-400">
                  {query.trim().length < 2 ? "Keep typing..." : "No videos found"}
                </p>
              )}
              {results.map((r) => (
                <button
                  key={r.videoId}
                  onClick={() => handleSelectResult(r)}
                  className="flex w-full items-center gap-3 border-t border-stone-100 px-5 py-3 text-left hover:bg-stone-50"
                >
                  {r.thumbnailUrl && (
                    <img
                      src={proxyImageUrl(r.thumbnailUrl)}
                      alt={r.title}
                      className="h-12 w-20 flex-shrink-0 rounded object-cover"
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 text-sm font-medium text-stone-900">
                      {r.title}
                    </p>
                    <p className="text-xs text-stone-500">
                      {r.channelTitle}
                      {r.viewCount ? ` · ${formatViews(r.viewCount)}` : ""}
                    </p>
                  </div>
                </button>
              ))}
            </div>

            {results.length === 0 && <div className="h-4" />}
          </>
        )}
      </div>
    </div>
  );
}
