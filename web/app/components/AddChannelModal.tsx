"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiJson, proxyImageUrl } from "../lib/api";

interface ChannelResult {
  channelId: string;
  name: string;
  description: string;
  thumbnailUrl: string;
  subscriberCount?: string;
}

interface PlaylistInfo {
  playlistId: string;
  title: string;
  thumbnailUrl: string;
  itemCount: number;
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

  // Playlist picker state
  const [showPlaylistPicker, setShowPlaylistPicker] = useState(false);
  const [playlists, setPlaylists] = useState<PlaylistInfo[]>([]);
  const [loadingPlaylists, setLoadingPlaylists] = useState(false);
  const [selectedPlaylistIds, setSelectedPlaylistIds] = useState<Set<string>>(new Set());
  const [allVideos, setAllVideos] = useState(true);

  // Pre-selected playlist from URL
  const [preselectedPlaylistId, setPreselectedPlaylistId] = useState<string | null>(null);
  const [existingSubId, setExistingSubId] = useState<string | null>(null);
  const [playlistFilter, setPlaylistFilter] = useState("");

  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setError("");
      setSelected(null);
      setAlreadySubscribed(false);
      setShowPlaylistPicker(false);
      setPlaylists([]);
      setSelectedPlaylistIds(new Set());
      setAllVideos(true);
      setPreselectedPlaylistId(null);
      setExistingSubId(null);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  const isUrl = (text: string) =>
    text.includes("youtube.com") || text.includes("youtu.be");

  const extractPlaylistId = (url: string): string | null => {
    const match = url.match(/[?&]list=([\w-]+)/);
    return match ? match[1] : null;
  };

  const handleInputChange = useCallback(
    (value: string) => {
      setQuery(value);
      setError("");
      setResults([]);

      if (debounceRef.current) clearTimeout(debounceRef.current);

      const trimmed = value.trim();
      if (!trimmed) return;

      if (isUrl(trimmed)) {
        return;
      }

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

    // Check if URL has a playlist ID
    const playlistId = extractPlaylistId(trimmed);
    if (playlistId) {
      setPreselectedPlaylistId(playlistId);
    }

    try {
      // Use search to resolve the channel without subscribing
      const data = await apiJson<ChannelResult[]>(
        `/api/channels/search?q=${encodeURIComponent(trimmed)}`,
      );
      if (data.length > 0) {
        setSelected(data[0]);
      } else {
        // Try to resolve via the POST endpoint but check for 409
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
          if (body.subscription_id) setExistingSubId(body.subscription_id);
        } else if (!res.ok) {
          setError(body.detail || "Couldn't find a channel at this URL");
        } else {
          onSubscribed();
          onClose();
        }
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
    if (showPlaylistPicker) {
      setShowPlaylistPicker(false);
      setPlaylistFilter("");
      return;
    }
    setSelected(null);
    setAlreadySubscribed(false);
    setError("");
    setPreselectedPlaylistId(null);
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  const handleChoosePlaylists = async () => {
    if (!selected) return;
    setLoadingPlaylists(true);
    setError("");
    try {
      const data = await apiJson<PlaylistInfo[]>(
        `/api/channels/playlists?channelId=${encodeURIComponent(selected.channelId)}`,
      );
      setPlaylists(data);
      setShowPlaylistPicker(true);
      setAllVideos(false);

      // Pre-select playlist if URL had a list= param
      if (preselectedPlaylistId) {
        setAllVideos(false);
        setSelectedPlaylistIds(new Set([preselectedPlaylistId]));
      }
    } catch {
      setError("Failed to load playlists");
    } finally {
      setLoadingPlaylists(false);
    }
  };

  const handleTogglePlaylist = (playlistId: string) => {
    setSelectedPlaylistIds((prev) => {
      const next = new Set(prev);
      if (next.has(playlistId)) {
        next.delete(playlistId);
      } else {
        next.add(playlistId);
      }
      return next;
    });
  };

  const handleSubscribe = async () => {
    if (!selected) return;
    setSubscribing(true);
    setError("");
    try {
      const playlistIds = allVideos ? null : Array.from(selectedPlaylistIds);

      // If editing an existing subscription, PATCH it
      if (existingSubId) {
        const res = await api(`/api/subscriptions/${existingSubId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ playlist_ids: playlistIds }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          setError(body.detail || "Failed to update");
        } else {
          onSubscribed();
          onClose();
        }
        return;
      }

      const res = await api("/api/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: `https://www.youtube.com/channel/${selected.channelId}`,
          playlist_ids: playlistIds,
        }),
      });
      if (res.status === 409) {
        const body = await res.json().catch(() => ({}));
        setAlreadySubscribed(true);
        if (body.subscription_id) setExistingSubId(body.subscription_id);
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
        {selected && showPlaylistPicker ? (
          // Phase 3: Playlist picker
          <div className="p-6">
            <h2 className="text-base font-semibold text-stone-900">
              Choose playlists
            </h2>
            <p className="mt-0.5 text-xs text-stone-500">
              {selected.name}
            </p>

            {playlists.length > 5 && (
              <input
                type="text"
                placeholder="Filter playlists..."
                value={playlistFilter}
                onChange={(e) => setPlaylistFilter(e.target.value)}
                className="mt-4 w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500"
              />
            )}
            <div className={`${playlists.length > 5 ? "mt-2" : "mt-4"} max-h-64 space-y-1 overflow-y-auto`}>
              {playlists.length === 0 && (
                <p className="py-2 text-xs text-stone-400">No playlists found on this channel</p>
              )}
              {playlists.filter((pl) => !playlistFilter || pl.title.toLowerCase().includes(playlistFilter.toLowerCase())).map((pl) => (
                <label
                  key={pl.playlistId}
                  className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 hover:bg-stone-50"
                >
                  <input
                    type="checkbox"
                    checked={selectedPlaylistIds.has(pl.playlistId)}
                    onChange={() => handleTogglePlaylist(pl.playlistId)}
                    className="flex-shrink-0 accent-stone-900"
                  />
                  {pl.thumbnailUrl ? (
                    <img
                      src={proxyImageUrl(pl.thumbnailUrl)}
                      alt={pl.title}
                      className="h-9 w-16 flex-shrink-0 rounded object-cover"
                    />
                  ) : (
                    <div className="h-9 w-16 flex-shrink-0 rounded bg-stone-100" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-stone-700">{pl.title}</p>
                    <p className="text-xs text-stone-400">{pl.itemCount} videos</p>
                  </div>
                </label>
              ))}
            </div>

            {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

            <div className="mt-5 flex gap-2">
              <button
                onClick={handleBack}
                className="flex-1 rounded-lg border border-stone-200 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
              >
                Back
              </button>
              <button
                onClick={handleSubscribe}
                disabled={subscribing || (!allVideos && selectedPlaylistIds.size === 0)}
                className="flex-1 rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
              >
                {subscribing ? "Subscribing..." : "Subscribe"}
              </button>
            </div>
          </div>
        ) : selected ? (
          // Phase 2: Confirm channel
          <div className="p-6 text-center">
            {selected.thumbnailUrl && (
              <img
                src={proxyImageUrl(selected.thumbnailUrl)}
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
            <div className="mt-5 flex flex-col gap-2">
              {!alreadySubscribed && (
                <>
                  <button
                    onClick={handleSubscribe}
                    disabled={subscribing}
                    className="w-full rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
                  >
                    {subscribing ? "Subscribing..." : "Subscribe to all playlists"}
                  </button>
                  <button
                    onClick={handleChoosePlaylists}
                    disabled={loadingPlaylists}
                    className="w-full rounded-lg border border-stone-200 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50 disabled:opacity-50"
                  >
                    {loadingPlaylists ? "Loading..." : "Choose specific playlists"}
                  </button>
                </>
              )}
              {alreadySubscribed && (
                <button
                  onClick={handleChoosePlaylists}
                  disabled={loadingPlaylists}
                  className="w-full rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
                >
                  {loadingPlaylists ? "Loading..." : "Edit playlists"}
                </button>
              )}
              <button
                onClick={handleBack}
                className="w-full rounded-lg px-4 py-2 text-sm text-stone-400 hover:text-stone-600"
              >
                Back
              </button>
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
                      src={proxyImageUrl(r.thumbnailUrl)}
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

            {results.length === 0 && <div className="h-4" />}
          </>
        )}
      </div>
    </div>
  );
}
