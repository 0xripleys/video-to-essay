import { Pool } from "pg";
import crypto from "crypto";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

function uid(): string {
  return crypto.randomUUID().replaceAll("-", "").slice(0, 12);
}

function now(): string {
  return new Date().toISOString();
}

// --- Types ---

export interface User {
  id: string;
  email: string;
  workos_user_id: string;
  created_at: string;
}

export interface Video {
  id: string;
  youtube_video_id: string;
  youtube_url: string;
  video_title: string | null;
  channel_id: string | null;
  downloaded_at: string | null;
  processed_at: string | null;
  error: string | null;
  created_at: string;
}

export interface Channel {
  id: string;
  youtube_channel_id: string;
  name: string;
  thumbnail_url: string | null;
  description: string | null;
  last_checked_at: string | null;
  created_at: string;
}

export interface Subscription {
  id: string;
  user_id: string;
  channel_id: string;
  playlist_ids: string[] | null;
  poll_interval_hours: number;
  active: boolean;
  created_at: string;
}

// --- Users ---

export async function getUserByWorkosId(
  workosUserId: string,
): Promise<User | null> {
  const { rows } = await pool.query(
    "SELECT * FROM users WHERE workos_user_id = $1",
    [workosUserId],
  );
  return rows[0] ?? null;
}

export async function upsertUser(
  email: string,
  workosUserId: string,
): Promise<User> {
  const existing = await getUserByWorkosId(workosUserId);
  if (existing) return existing;
  const id = uid();
  await pool.query(
    "INSERT INTO users (id, email, workos_user_id, created_at) VALUES ($1, $2, $3, $4)",
    [id, email, workosUserId, now()],
  );
  return { id, email, workos_user_id: workosUserId, created_at: now() };
}

// --- Videos ---

export async function getOrCreateVideo(
  youtubeVideoId: string,
  youtubeUrl: string,
): Promise<Video> {
  const { rows } = await pool.query(
    "SELECT * FROM videos WHERE youtube_video_id = $1",
    [youtubeVideoId],
  );
  if (rows[0]) return rows[0];
  const id = uid();
  const ts = now();
  await pool.query(
    "INSERT INTO videos (id, youtube_video_id, youtube_url, created_at) VALUES ($1, $2, $3, $4)",
    [id, youtubeVideoId, youtubeUrl, ts],
  );
  return {
    id,
    youtube_video_id: youtubeVideoId,
    youtube_url: youtubeUrl,
    video_title: null,
    channel_id: null,
    downloaded_at: null,
    processed_at: null,
    error: null,
    created_at: ts,
  };
}

export async function getVideo(videoId: string): Promise<Video | null> {
  const { rows } = await pool.query("SELECT * FROM videos WHERE id = $1", [
    videoId,
  ]);
  return rows[0] ?? null;
}

export async function listUserVideos(
  userId: string,
): Promise<(Video & { channel_name?: string; source?: string; delivery_sent_at?: string })[]> {
  const { rows } = await pool.query(
    `SELECT DISTINCT ON (v.id) v.*, c.name as channel_name,
            d.source, d.sent_at as delivery_sent_at
     FROM videos v
     LEFT JOIN channels c ON c.id = v.channel_id
     LEFT JOIN deliveries d ON d.video_id = v.id AND d.user_id = $1
     WHERE d.user_id = $1
        OR v.channel_id IN (
            SELECT s.channel_id FROM subscriptions s
            WHERE s.user_id = $1 AND s.active = TRUE
        )
     ORDER BY v.id, v.created_at DESC`,
    [userId],
  );
  return rows;
}

// --- Deliveries ---

export async function createDelivery(
  videoId: string,
  userId: string,
  source: string,
): Promise<string | null> {
  const id = uid();
  try {
    await pool.query(
      "INSERT INTO deliveries (id, video_id, user_id, source, created_at) VALUES ($1, $2, $3, $4, $5)",
      [id, videoId, userId, source, now()],
    );
    return id;
  } catch (err: unknown) {
    if (
      err instanceof Error &&
      err.message.includes("unique constraint")
    ) {
      return null;
    }
    throw err;
  }
}

// --- Channels ---

export async function getOrCreateChannel(
  youtubeChannelId: string,
  name: string,
  thumbnailUrl?: string,
  description?: string,
): Promise<Channel> {
  const { rows } = await pool.query(
    "SELECT * FROM channels WHERE youtube_channel_id = $1",
    [youtubeChannelId],
  );
  if (rows[0]) return rows[0];
  const id = uid();
  const ts = now();
  await pool.query(
    "INSERT INTO channels (id, youtube_channel_id, name, thumbnail_url, description, created_at) VALUES ($1, $2, $3, $4, $5, $6)",
    [id, youtubeChannelId, name, thumbnailUrl ?? null, description ?? null, ts],
  );
  return {
    id,
    youtube_channel_id: youtubeChannelId,
    name,
    thumbnail_url: thumbnailUrl ?? null,
    description: description ?? null,
    last_checked_at: null,
    created_at: ts,
  };
}

// --- Subscriptions ---

export async function createSubscription(
  userId: string,
  channelId: string,
  playlistIds: string[] | null = null,
): Promise<string> {
  const id = uid();
  await pool.query(
    "INSERT INTO subscriptions (id, user_id, channel_id, playlist_ids, poll_interval_hours, active, created_at) VALUES ($1, $2, $3, $4, 1, TRUE, $5)",
    [id, userId, channelId, playlistIds, now()],
  );
  return id;
}

export async function listUserSubscriptions(
  userId: string,
): Promise<(Subscription & { youtube_channel_id: string; channel_name: string; thumbnail_url: string | null; description: string | null; video_count: number })[]> {
  const { rows } = await pool.query(
    `SELECT s.*, c.youtube_channel_id, c.name as channel_name, c.thumbnail_url, c.description,
       (SELECT COUNT(*) FROM videos v
        JOIN deliveries d ON d.video_id = v.id AND d.user_id = s.user_id
        WHERE v.channel_id = c.id)::int as video_count
     FROM subscriptions s
     JOIN channels c ON c.id = s.channel_id
     WHERE s.user_id = $1 AND s.active = TRUE
     ORDER BY s.created_at DESC`,
    [userId],
  );
  return rows;
}

export async function getSubscriptionByUserAndChannel(
  userId: string,
  channelId: string,
): Promise<Subscription | null> {
  const { rows } = await pool.query(
    "SELECT * FROM subscriptions WHERE user_id = $1 AND channel_id = $2 AND active = TRUE",
    [userId, channelId],
  );
  return rows[0] ?? null;
}

export async function getSubscription(
  subId: string,
): Promise<Subscription | null> {
  const { rows } = await pool.query(
    "SELECT * FROM subscriptions WHERE id = $1",
    [subId],
  );
  return rows[0] ?? null;
}

export async function deactivateSubscription(subId: string): Promise<void> {
  await pool.query(
    "UPDATE subscriptions SET active = FALSE WHERE id = $1",
    [subId],
  );
}

export async function updateSubscriptionInterval(
  subId: string,
  pollIntervalHours: number,
): Promise<void> {
  await pool.query(
    "UPDATE subscriptions SET poll_interval_hours = $1 WHERE id = $2",
    [pollIntervalHours, subId],
  );
}

export async function updateSubscriptionPlaylists(
  subId: string,
  playlistIds: string[] | null,
): Promise<void> {
  await pool.query(
    "UPDATE subscriptions SET playlist_ids = $1 WHERE id = $2",
    [playlistIds, subId],
  );
}
