import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/lib/auth";
import {
  getOrCreateChannel,
  createSubscription,
  listUserSubscriptions,
  getSubscriptionByUserAndChannel,
} from "@/app/lib/db";
import { resolveChannel } from "@/app/lib/youtube";
import { getPostHogClient } from "@/app/lib/posthog";

export async function GET() {
  let user;
  try {
    user = await requireAuth();
  } catch {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const subs = await listUserSubscriptions(user.id);
  return NextResponse.json(subs);
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
  const playlistIds: string[] | undefined = body.playlist_ids;

  if (!url) {
    return NextResponse.json({ detail: "URL is required" }, { status: 422 });
  }

  const channelInfo = await resolveChannel(url);
  if (!channelInfo) {
    return NextResponse.json(
      {
        detail:
          "Could not find YouTube channel. Use a URL like youtube.com/@handle, youtube.com/channel/UC..., or a playlist URL.",
      },
      { status: 422 },
    );
  }

  const channel = await getOrCreateChannel(
    channelInfo.channelId,
    channelInfo.name,
    channelInfo.thumbnailUrl,
    channelInfo.description,
  );

  try {
    const subId = await createSubscription(
      user.id,
      channel.id,
      playlistIds ?? null,
    );
    getPostHogClient()?.capture({
      distinctId: user.id,
      event: "channel_subscribed",
      properties: {
        channel_name: channelInfo.name,
        youtube_channel_id: channelInfo.channelId,
      },
    });
    return NextResponse.json({
      subscription_id: subId,
      channel_id: channel.id,
      youtube_channel_id: channelInfo.channelId,
      name: channelInfo.name,
      thumbnail_url: channelInfo.thumbnailUrl,
      description: channelInfo.description,
    });
  } catch {
    const existing = await getSubscriptionByUserAndChannel(user.id, channel.id);
    return NextResponse.json(
      {
        detail: "Already subscribed",
        subscription_id: existing?.id,
        youtube_channel_id: channelInfo.channelId,
        name: channelInfo.name,
        thumbnail_url: channelInfo.thumbnailUrl,
        description: channelInfo.description,
      },
      { status: 409 },
    );
  }
}
