export interface YouTubeChannelInfo {
  channelId: string;
  name: string;
  description: string;
  thumbnailUrl: string;
  subscriberCount?: string;
}

export async function resolveChannel(
  input: string,
): Promise<YouTubeChannelInfo | null> {
  const apiKey = process.env.YOUTUBE_API_KEY;
  if (!apiKey) throw new Error("YOUTUBE_API_KEY must be set");

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
    thumbnailUrl:
      item.snippet.thumbnails?.medium?.url ??
      item.snippet.thumbnails?.default?.url ??
      "",
  };
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

  // Fetch subscriber counts for all channels in one request
  const channelIds = items.map((item: { id: { channelId: string } }) => item.id.channelId).join(",");
  const statsUrl = `https://www.googleapis.com/youtube/v3/channels?id=${channelIds}&part=statistics&key=${apiKey}`;
  const statsRes = await fetch(statsUrl);
  const statsMap = new Map<string, string>();
  if (statsRes.ok) {
    const statsData = await statsRes.json();
    for (const ch of statsData.items ?? []) {
      statsMap.set(ch.id, ch.statistics?.subscriberCount ?? "0");
    }
  }

  return items.map((item: { id: { channelId: string }; snippet: { title: string; description: string; thumbnails: { medium?: { url: string }; default?: { url: string } } } }) => ({
    channelId: item.id.channelId,
    name: item.snippet.title,
    description: item.snippet.description,
    thumbnailUrl:
      item.snippet.thumbnails?.medium?.url ??
      item.snippet.thumbnails?.default?.url ??
      "",
    subscriberCount: statsMap.get(item.id.channelId) ?? "0",
  }));
}
