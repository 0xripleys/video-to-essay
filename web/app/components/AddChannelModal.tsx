"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiJson } from "../lib/api";

interface ChannelResult {
  channelId: string;
  name: string;
  description: string;
  thumbnailUrl: string;
  subscriberCount?: string;
}

function formatSubscribers(count: string | undefined): string {
  const n = parseInt(count ?? "0", 10);
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M subscribers`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}K subscribers`;
  return `${n} subscribers`;
}

export default function AddChannelModal({
  open,
  onClose,
  onSubscribed,
}: {
  open: boolean;
  onClose: () => void;
  onSubscribed: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ChannelResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [subscribing, setSubscribing] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<ChannelResult | null>(null);
  const [alreadySubscribed, setAlreadySubscribed] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setError("");
      setSelected(null);
      setAlreadySubscribed(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  const isUrl = (text: string) =>
    text.includes("youtube.com") || text.includes("youtu.be");

  const handleInputChange = useCallback(
    (value: string) => {
      setQuery(value);
      setError("");
      setResults([]);

      if (debounceRef.current) clearTimeout(debounceRef.current);

      const trimmed = value.trim();
      if (!trimmed) return;

      if (isUrl(trimmed)) {
        // URL mode: resolve on Enter, not on type
        return;
      }

      // Search mode: debounced
      debounceRef.current = setTimeout(async () => {
        setSearching(true);
        try {
          const data = await apiJson<ChannelResult[]>(
            `/api/channels/search?q=${encodeURIComponent(trimmed)}`,
          );
          setResults(data);
        } catch {
          setResults([]);
        } finally {
          setSearching(false);
        }
      }, 300);
    },
    [],
  );

  const handleKeyDown = async (e: React.KeyboardEvent) => {
    if (e.key !== "Enter") return;
    const trimmed = query.trim();
    if (!trimmed || !isUrl(trimmed)) return;

    e.preventDefault();
    setResolving(true);
    setError("");
    try {
      const res = await api("/api/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmed }),
      });
      const body = await res.json();
      if (res.status === 409) {
        setSelected({
          channelId: body.youtube_channel_id,
          name: body.name ?? "Channel",
          description: body.description ?? "",
          thumbnailUrl: body.thumbnail_url ?? "",
          subscriberCount: body.subscriber_count,
        });
        setAlreadySubscribed(true);
      } else if (!res.ok) {
        setError(body.detail || "Couldn't find a channel at this URL");
      } else {
        // Successfully subscribed directly — show confirmation then close
        onSubscribed();
        onClose();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setResolving(false);
    }
  };

  const handleSelectResult = (result: ChannelResult) => {
    setSelected(result);
    setResults([]);
    setAlreadySubscribed(false);
  };

  const handleBack = () => {
    setSelected(null);
    setAlreadySubscribed(false);
    setError("");
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  const handleSubscribe = async () => {
    if (!selected) return;
    setSubscribing(true);
    setError("");
    try {
      const res = await api("/api/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: `https://www.youtube.com/channel/${selected.channelId}`,
        }),
      });
      if (res.status === 409) {
        setAlreadySubscribed(true);
      } else if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail || "Failed to subscribe");
      } else {
        onSubscribed();
        onClose();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubscribing(false);
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
          // Phase 2: Confirm
          <div className="p-6 text-center">
            {selected.thumbnailUrl && (
              <img
                src={selected.thumbnailUrl}
                alt={selected.name}
                className="mx-auto h-14 w-14 rounded-full object-cover"
              />
            )}
            <p className="mt-3 text-base font-semibold text-stone-900">
              {selected.name}
            </p>
            {selected.subscriberCount && (
              <p className="mt-0.5 text-xs text-stone-500">
                {formatSubscribers(selected.subscriberCount)}
              </p>
            )}
            {selected.description && (
              <p className="mx-auto mt-2 max-w-xs text-xs leading-relaxed text-stone-400 line-clamp-3">
                {selected.description}
              </p>
            )}
            {alreadySubscribed && (
              <p className="mt-3 text-sm text-stone-500">
                You&apos;re already subscribed to this channel.
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
              {!alreadySubscribed && (
                <button
                  onClick={handleSubscribe}
                  disabled={subscribing}
                  className="flex-1 rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
                >
                  {subscribing ? "Subscribing..." : "Subscribe"}
                </button>
              )}
            </div>
          </div>
        ) : (
          // Phase 1: Search
          <>
            <div className="p-5 pb-0">
              <h2 className="text-base font-semibold text-stone-900">
                Add channel
              </h2>
              <p className="mt-0.5 text-xs text-stone-500">
                Search for a channel or paste a YouTube URL
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
              {error && (
                <p className="mt-2 text-xs text-red-600">{error}</p>
              )}
              {resolving && (
                <p className="mt-2 text-xs text-stone-400">
                  Resolving channel...
                </p>
              )}
            </div>

            <div className="mt-1">
              {searching && (
                <p className="px-5 py-3 text-xs text-stone-400">
                  Searching...
                </p>
              )}
              {!searching && results.length === 0 && query.trim() && !isUrl(query) && (
                <p className="px-5 py-3 text-xs text-stone-400">
                  {query.trim().length < 2
                    ? "Keep typing..."
                    : "No channels found"}
                </p>
              )}
              {results.map((r) => (
                <button
                  key={r.channelId}
                  onClick={() => handleSelectResult(r)}
                  className="flex w-full items-center gap-3 border-t border-stone-100 px-5 py-3 text-left hover:bg-stone-50"
                >
                  {r.thumbnailUrl && (
                    <img
                      src={r.thumbnailUrl}
                      alt={r.name}
                      className="h-9 w-9 flex-shrink-0 rounded-full object-cover"
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-stone-900">
                      {r.name}
                    </p>
                    <p className="text-xs text-stone-500">
                      {formatSubscribers(r.subscriberCount)}
                    </p>
                  </div>
                </button>
              ))}
            </div>

            {/* Bottom padding when no results */}
            {results.length === 0 && <div className="h-4" />}
          </>
        )}
      </div>
    </div>
  );
}
