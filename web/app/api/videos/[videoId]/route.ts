import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/lib/auth";
import { getVideo } from "@/app/lib/db";
import { getEssayFromS3 } from "@/app/lib/s3";

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
    result.essay_md = await getEssayFromS3(video.youtube_video_id);
  }

  return NextResponse.json(result);
}
