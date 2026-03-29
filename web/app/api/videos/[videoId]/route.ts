import { NextRequest, NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";
import { requireAuth } from "@/app/lib/auth";
import { getVideo } from "@/app/lib/db";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ videoId: string }> },
) {
  let user;
  try {
    user = await requireAuth();
  } catch {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const { videoId } = await params;
  const video = await getVideo(videoId);
  if (!video) {
    return NextResponse.json({ detail: "Video not found" }, { status: 404 });
  }

  let status = "pending_download";
  if (video.error) status = "failed";
  else if (video.processed_at) status = "done";
  else if (video.downloaded_at) status = "processing";

  const result: Record<string, unknown> = {
    id: video.id,
    youtube_video_id: video.youtube_video_id,
    youtube_url: video.youtube_url,
    video_title: video.video_title,
    status,
    error: video.error,
    created_at: video.created_at,
  };

  if (status === "done") {
    const runsDir = process.env.RUNS_DIR || path.join(process.cwd(), "..", "runs");
    const essayPath = path.join(
      runsDir,
      video.youtube_video_id,
      "05_place_images",
      "essay_final.md",
    );
    try {
      result.essay_md = await readFile(essayPath, "utf-8");
    } catch {
      // Essay file not found — that's fine
    }
  }

  return NextResponse.json(result);
}
