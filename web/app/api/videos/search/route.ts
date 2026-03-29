import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/lib/auth";
import { searchVideos } from "@/app/lib/youtube";

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

  const results = await searchVideos(q);
  return NextResponse.json(results);
}
