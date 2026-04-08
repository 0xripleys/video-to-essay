import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/lib/auth";
import {
  getSubscription,
  deactivateSubscription,
  updateSubscriptionInterval,
  updateSubscriptionPlaylists,
  updateSubscriptionExcludeLivestreams,
} from "@/app/lib/db";
import { getPostHogClient } from "@/app/lib/posthog";

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ subId: string }> },
) {
  let user;
  try {
    user = await requireAuth();
  } catch {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const { subId } = await params;
  const sub = await getSubscription(subId);
  if (!sub || sub.user_id !== user.id) {
    return NextResponse.json(
      { detail: "Subscription not found" },
      { status: 404 },
    );
  }

  await deactivateSubscription(subId);
  getPostHogClient()?.capture({
    distinctId: user.id,
    event: "channel_unsubscribed",
    properties: { subscription_id: subId },
  });
  return NextResponse.json({ status: "unsubscribed" });
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ subId: string }> },
) {
  let user;
  try {
    user = await requireAuth();
  } catch {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const { subId } = await params;
  const sub = await getSubscription(subId);
  if (!sub || sub.user_id !== user.id) {
    return NextResponse.json(
      { detail: "Subscription not found" },
      { status: 404 },
    );
  }

  const body = await request.json();
  if (body.poll_interval_hours !== undefined) {
    await updateSubscriptionInterval(subId, body.poll_interval_hours);
  }
  if ("playlist_ids" in body) {
    await updateSubscriptionPlaylists(subId, body.playlist_ids ?? null);
  }
  if ("exclude_livestreams" in body) {
    await updateSubscriptionExcludeLivestreams(subId, body.exclude_livestreams ?? false);
  }
  return NextResponse.json({ status: "updated" });
}
