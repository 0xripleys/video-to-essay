export interface YouTubeChannelInfo {
  channelId: string;
  name: string;
  description: string;
  thumbnailUrl: string;
  subscriberCount?: string;
}

function ensureHttps(url: string): string {
  if (url.startsWith("//")) return `https:${url}`;
  if (url.startsWith("http://")) return url.replace("http://", "https://");
  return url;
}

function extractThumbnail(thumbnails: { medium?: { url: string }; default?: { url: string } }): string {
  const raw = thumbnails?.medium?.url ?? thumbnails?.default?.url ?? "";
  return raw ? ensureHttps(raw) : "";
}

export function extractPlaylistId(input: string): string | null {
  const listMatch = input.match(/[?&]list=([\w-]+)/);
  if (listMatch) return listMatch[1];
  const playlistMatch = input.match(/playlist\?list=([\w-]+)/);
  if (playlistMatch) return playlistMatch[1];
  return null;
}

export async function resolveChannel(
  input: string,
): Promise<YouTubeChannelInfo | null> {
  const apiKey = process.env.YOUTUBE_API_KEY;
  if (!apiKey) throw new Error("YOUTUBE_API_KEY must be set");

  // If it's a playlist URL, resolve the channel from the playlist
  const playlistId = extractPlaylistId(input);
  if (playlistId && !input.match(/channel\/(UC[\w-]{22})/) && !input.match(/@([\w.-]+)/)) {
    return resolveChannelFromPlaylist(playlistId, apiKey);
  }

  // If it's already a UC... channel ID, look it up directly
  const directMatch = input.match(/channel\/(UC[\w-]{22})/);
  if (directMatch) {
    return fetchChannelById(directMatch[1], apiKey);
  }

  // Extract handle from URL like youtube.com/@Handle
  const handleMatch = input.match(/@([\w.-]+)/);
  if (handleMatch) {
    return fetchChannelByHandle(handleMatch[1], apiKey);
  }

  // Try channel_id= query param
  const paramMatch = input.match(/channel_id=(UC[\w-]{22})/);
  if (paramMatch) {
    return fetchChannelById(paramMatch[1], apiKey);
  }

  return null;
}

async function resolveChannelFromPlaylist(
  playlistId: string,
  apiKey: string,
): Promise<YouTubeChannelInfo | null> {
  const url = `https://www.googleapis.com/youtube/v3/playlists?id=${encodeURIComponent(playlistId)}&part=snippet&key=${apiKey}`;
  const res = await fetch(url);
  if (!res.ok) return null;
  const data = await res.json();
  const item = data.items?.[0];
  if (!item) return null;
  const channelId = item.snippet.channelId;
  return fetchChannelById(channelId, apiKey);
}

async function fetchChannelByHandle(
  handle: string,
  apiKey: string,
): Promise<YouTubeChannelInfo | null> {
  const url = `https://www.googleapis.com/youtube/v3/channels?forHandle=${encodeURIComponent(handle)}&part=snippet&key=${apiKey}`;
  return fetchAndParse(url);
}

async function fetchChannelById(
  channelId: string,
  apiKey: string,
): Promise<YouTubeChannelInfo | null> {
  const url = `https://www.googleapis.com/youtube/v3/channels?id=${encodeURIComponent(channelId)}&part=snippet&key=${apiKey}`;
  return fetchAndParse(url);
}

async function fetchAndParse(url: string): Promise<YouTubeChannelInfo | null> {
  const res = await fetch(url);
  if (!res.ok) return null;

  const data = await res.json();
  const item = data.items?.[0];
  if (!item) return null;

  return {
    channelId: item.id,
    name: item.snippet.title,
    description: item.snippet.description,
    thumbnailUrl: extractThumbnail(item.snippet.thumbnails),
  };
}

export interface YouTubeVideoInfo {
  videoId: string;
  title: string;
  channelTitle: string;
  thumbnailUrl: string;
  viewCount?: string;
  publishedAt?: string;
}

export async function getVideoById(
  videoId: string,
): Promise<YouTubeVideoInfo | null> {
  const apiKey = process.env.YOUTUBE_API_KEY;
  if (!apiKey) throw new Error("YOUTUBE_API_KEY must be set");

  const url = `https://www.googleapis.com/youtube/v3/videos?id=${encodeURIComponent(videoId)}&part=snippet,statistics&key=${apiKey}`;
  const res = await fetch(url);
  if (!res.ok) return null;

  const data = await res.json();
  const item = data.items?.[0];
  if (!item) return null;

  return {
    videoId: item.id,
    title: item.snippet.title,
    channelTitle: item.snippet.channelTitle,
    thumbnailUrl: extractThumbnail(item.snippet.thumbnails),
    viewCount: item.statistics?.viewCount ?? "0",
    publishedAt: item.snippet.publishedAt,
  };
}

export async function searchVideos(
  query: string,
): Promise<YouTubeVideoInfo[]> {
  const apiKey = process.env.YOUTUBE_API_KEY;
  if (!apiKey) throw new Error("YOUTUBE_API_KEY must be set");

  const searchUrl = `https://www.googleapis.com/youtube/v3/search?q=${encodeURIComponent(query)}&type=video&maxResults=5&part=snippet&key=${apiKey}`;
  const searchRes = await fetch(searchUrl);
  if (!searchRes.ok) return [];

  const searchData = await searchRes.json();
  const items = searchData.items;
  if (!items?.length) return [];

  // Fetch view counts for all videos in one request
  const videoIds = items.map((item: { id: { videoId: string } }) => item.id.videoId).join(",");
  const statsUrl = `https://www.googleapis.com/youtube/v3/videos?id=${videoIds}&part=statistics&key=${apiKey}`;
  const statsRes = await fetch(statsUrl);
  const statsMap = new Map<string, string>();
  if (statsRes.ok) {
    const statsData = await statsRes.json();
    for (const v of statsData.items ?? []) {
      statsMap.set(v.id, v.statistics?.viewCount ?? "0");
    }
  }

  return items.map((item: { id: { videoId: string }; snippet: { title: string; channelTitle: string; publishedAt: string; thumbnails: { medium?: { url: string }; default?: { url: string } } } }) => ({
    videoId: item.id.videoId,
    title: item.snippet.title,
    channelTitle: item.snippet.channelTitle,
    thumbnailUrl: extractThumbnail(item.snippet.thumbnails),
    viewCount: statsMap.get(item.id.videoId) ?? "0",
    publishedAt: item.snippet.publishedAt,
  }));
}

export interface YouTubePlaylistInfo {
  playlistId: string;
  title: string;
  thumbnailUrl: string;
  itemCount: number;
}

export async function listChannelPlaylists(
  channelId: string,
): Promise<YouTubePlaylistInfo[]> {
  const apiKey = process.env.YOUTUBE_API_KEY;
  if (!apiKey) throw new Error("YOUTUBE_API_KEY must be set");

  const results: YouTubePlaylistInfo[] = [];
  let pageToken: string | undefined;

  do {
    const params = new URLSearchParams({
      channelId,
      part: "snippet,contentDetails",
      maxResults: "50",
      key: apiKey,
    });
    if (pageToken) params.set("pageToken", pageToken);

    const res = await fetch(`https://www.googleapis.com/youtube/v3/playlists?${params}`);
    if (!res.ok) break;

    const data = await res.json();
    for (const item of data.items ?? []) {
      results.push({
        playlistId: item.id,
        title: item.snippet.title,
        thumbnailUrl: extractThumbnail(item.snippet.thumbnails),
        itemCount: item.contentDetails?.itemCount ?? 0,
      });
    }
    pageToken = data.nextPageToken;
  } while (pageToken);

  return results;
}

export async function searchChannels(
  query: string,
): Promise<YouTubeChannelInfo[]> {
  const apiKey = process.env.YOUTUBE_API_KEY;
  if (!apiKey) throw new Error("YOUTUBE_API_KEY must be set");

  const searchUrl = `https://www.googleapis.com/youtube/v3/search?q=${encodeURIComponent(query)}&type=channel&maxResults=5&part=snippet&key=${apiKey}`;
  const searchRes = await fetch(searchUrl);
  if (!searchRes.ok) return [];

  const searchData = await searchRes.json();
  const items = searchData.items;
  if (!items?.length) return [];

  // Fetch subscriber counts and proper channel thumbnails in one request
  const channelIds = items.map((item: { id: { channelId: string } }) => item.id.channelId).join(",");
  const detailsUrl = `https://www.googleapis.com/youtube/v3/channels?id=${channelIds}&part=snippet,statistics&key=${apiKey}`;
  const detailsRes = await fetch(detailsUrl);
  const statsMap = new Map<string, string>();
  const thumbMap = new Map<string, string>();
  if (detailsRes.ok) {
    const detailsData = await detailsRes.json();
    for (const ch of detailsData.items ?? []) {
      statsMap.set(ch.id, ch.statistics?.subscriberCount ?? "0");
      thumbMap.set(ch.id, extractThumbnail(ch.snippet?.thumbnails ?? {}));
    }
  }

  return items.map((item: { id: { channelId: string }; snippet: { title: string; description: string } }) => ({
    channelId: item.id.channelId,
    name: item.snippet.title,
    description: item.snippet.description,
    thumbnailUrl: thumbMap.get(item.id.channelId) ?? "",
    subscriberCount: statsMap.get(item.id.channelId) ?? "0",
  }));
}
