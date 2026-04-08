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
  playlist_ids: string[] | null;
  exclude_livestreams: boolean;
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

interface PlaylistInfo {
  playlistId: string;
  title: string;
  thumbnailUrl: string;
  itemCount: number;
}

function EditPlaylistsModal({
  channel,
  onClose,
  onSaved,
}: {
  channel: Channel;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [playlists, setPlaylists] = useState<PlaylistInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(channel.playlist_ids ?? []),
  );
  const [allVideos, setAllVideos] = useState(!channel.playlist_ids);
  const [excludeLivestreams, setExcludeLivestreams] = useState(channel.exclude_livestreams ?? false);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    apiJson<PlaylistInfo[]>(
      `/api/channels/playlists?channelId=${encodeURIComponent(channel.youtube_channel_id)}`,
    )
      .then(setPlaylists)
      .finally(() => setLoading(false));
  }, [channel.youtube_channel_id]);

  const handleToggle = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await api(`/api/subscriptions/${channel.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          playlist_ids: allVideos ? null : Array.from(selectedIds),
          exclude_livestreams: allVideos ? false : excludeLivestreams,
        }),
      });
      if (res.ok) {
        onSaved();
        onClose();
      }
    } finally {
      setSaving(false);
    }
  };

  const filtered = playlists.filter(
    (pl) => !filter || pl.title.toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-[15vh]"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="text-base font-semibold text-stone-900">
          Edit playlists
        </h2>
        <p className="mt-0.5 text-xs text-stone-500">{channel.channel_name}</p>

        <div className="mt-4 space-y-2">
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-stone-200 px-3 py-2 hover:bg-stone-50">
            <input
              type="radio"
              checked={allVideos}
              onChange={() => {
                setAllVideos(true);
                setSelectedIds(new Set());
              }}
              className="accent-stone-900"
            />
            <span className="text-sm text-stone-900">All playlists</span>
          </label>
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-stone-200 px-3 py-2 hover:bg-stone-50">
            <input
              type="radio"
              checked={!allVideos}
              onChange={() => setAllVideos(false)}
              className="accent-stone-900"
            />
            <span className="text-sm text-stone-900">Specific playlists</span>
          </label>
        </div>

        {!allVideos && (
          <>
            {playlists.length > 5 && (
              <input
                type="text"
                placeholder="Filter playlists..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="mt-3 w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500"
              />
            )}
            <div className="mt-2 max-h-48 space-y-1 overflow-y-auto">
              <label
                className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 hover:bg-stone-50"
              >
                <input
                  type="checkbox"
                  checked={!excludeLivestreams}
                  onChange={() => setExcludeLivestreams(!excludeLivestreams)}
                  className="flex-shrink-0 accent-stone-900"
                />
                <div className="flex h-9 w-16 flex-shrink-0 items-center justify-center rounded bg-red-50">
                  <span className="text-xs text-red-500">LIVE</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-stone-700">Live Streams</p>
                  <p className="text-xs text-stone-400">Include live stream recordings</p>
                </div>
              </label>
              {loading && (
                <p className="py-2 text-xs text-stone-400">Loading playlists...</p>
              )}
              {!loading && filtered.length === 0 && (
                <p className="py-2 text-xs text-stone-400">No playlists found</p>
              )}
              {filtered.map((pl) => (
                <label
                  key={pl.playlistId}
                  className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 hover:bg-stone-50"
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.has(pl.playlistId)}
                    onChange={() => handleToggle(pl.playlistId)}
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
          </>
        )}

        <div className="mt-5 flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 rounded-lg border border-stone-200 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || (!allVideos && selectedIds.size === 0)}
            className="flex-1 rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save"}
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
  const [editTarget, setEditTarget] = useState<Channel | null>(null);

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
      <div className="mx-auto max-w-2xl px-4 py-6 md:px-6 md:py-8">
        <h1 className="text-xl font-bold tracking-tight">Channels</h1>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6 md:px-6 md:py-8">
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
                    {ch.playlist_ids
                      ? `${ch.playlist_ids.length} playlist${ch.playlist_ids.length === 1 ? "" : "s"}`
                      : "All playlists"}
                    {" "}&middot;{" "}
                    {ch.video_count} {ch.video_count === 1 ? "video" : "videos"}{" "}
                    &middot; Subscribed {subscriptionAge(ch.created_at)}
                  </p>
                </div>
                <div className="flex flex-shrink-0 gap-2">
                  <button
                    onClick={() => setEditTarget(ch)}
                    className="rounded-lg border border-stone-200 px-3 py-1.5 text-xs text-stone-500 transition-colors hover:border-stone-300 hover:text-stone-700"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => setUnsubTarget(ch)}
                    className="rounded-lg border border-stone-200 px-3 py-1.5 text-xs text-stone-500 transition-colors hover:border-stone-300 hover:text-stone-700"
                  >
                    Unsubscribe
                  </button>
                </div>
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
      {editTarget && (
        <EditPlaylistsModal
          channel={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={() => fetchChannels()}
        />
      )}
    </div>
  );
}
