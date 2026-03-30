import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/lib/auth";
import { getVideoById, searchVideos } from "@/app/lib/youtube";

export async function GET(request: NextRequest) {
  try {
    await requireAuth();
  } catch {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const q = request.nextUrl.searchParams.get("q")?.trim();
  if (!q) {
    return NextResponse.json(
      { detail: "Query parameter q is required" },
      { status: 422 },
    );
  }

  // If query looks like a video ID (11 chars, alphanumeric + dash/underscore),
  // use direct lookup instead of search for reliable results
  if (/^[\w-]{11}$/.test(q)) {
    const video = await getVideoById(q);
    return NextResponse.json(video ? [video] : []);
  }

  const results = await searchVideos(q);
  return NextResponse.json(results);
}
