import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/lib/auth";
import { listChannelPlaylists } from "@/app/lib/youtube";

export async function GET(request: NextRequest) {
  try {
    await requireAuth();
  } catch {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const channelId = request.nextUrl.searchParams.get("channelId");
  if (!channelId) {
    return NextResponse.json(
      { detail: "channelId query param is required" },
      { status: 422 },
    );
  }

  const playlists = await listChannelPlaylists(channelId);
  return NextResponse.json(playlists);
}
