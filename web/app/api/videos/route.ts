import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/lib/auth";
import { getOrCreateVideo, createDelivery, listUserVideos } from "@/app/lib/db";
import { getPostHogClient } from "@/app/lib/posthog";

const YOUTUBE_URL_RE =
  /^https?:\/\/(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/)[\w-]{11}/;

export async function GET() {
  let user;
  try {
    user = await requireAuth();
  } catch {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const videos = await listUserVideos(user.id);
  const result = videos.map((v) => {
    let status = "pending_download";
    if (v.error) status = "failed";
    else if (v.processed_at) status = "done";
    else if (v.downloaded_at) status = "processing";

    return {
      id: v.id,
      youtube_video_id: v.youtube_video_id,
      youtube_url: v.youtube_url,
      video_title: v.video_title,
      channel_name: v.channel_name,
      source: v.source,
      status,
      error: v.error,
      delivery_sent_at: v.delivery_sent_at,
      created_at: v.created_at,
    };
  });

  return NextResponse.json(result);
}

export async function POST(request: NextRequest) {
  let user;
  try {
    user = await requireAuth();
  } catch {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const body = await request.json();
  const url: string = body.url;

  if (!url || !YOUTUBE_URL_RE.test(url)) {
    return NextResponse.json({ detail: "Invalid YouTube URL" }, { status: 422 });
  }

  const videoIdMatch = url.match(/(?:v=|youtu\.be\/)([\w-]{11})/);
  if (!videoIdMatch) {
    return NextResponse.json(
      { detail: "Could not extract video ID" },
      { status: 422 },
    );
  }
  const youtubeVideoId = videoIdMatch[1];

  const video = await getOrCreateVideo(youtubeVideoId, url);
  await createDelivery(video.id, user.id, "one_off");

  getPostHogClient()?.capture({
    distinctId: user.id,
    event: "video_conversion_requested",
    properties: { youtube_video_id: youtubeVideoId },
  });

  return NextResponse.json({ id: video.id });
}
