import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/lib/auth";
import { getLatestChannelVideo } from "@/app/lib/youtube";

export async function GET(request: NextRequest) {
  try {
    await requireAuth();
  } catch {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const channelId = request.nextUrl.searchParams.get("channelId");
  if (!channelId) {
    return NextResponse.json(
      { detail: "channelId is required" },
      { status: 422 },
    );
  }

  const video = await getLatestChannelVideo(channelId);
  if (!video) {
    return NextResponse.json(
      { detail: "No videos found" },
      { status: 404 },
    );
  }

  return NextResponse.json(video);
}
