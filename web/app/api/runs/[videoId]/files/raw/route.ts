import { NextRequest, NextResponse } from "next/server";
import { requireAdminRoute } from "@/app/lib/admin";
import { streamRunArtifact } from "@/app/lib/s3";

const CONTENT_TYPE_BY_EXT: Record<string, string> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  gif: "image/gif",
  webp: "image/webp",
  mp3: "audio/mpeg",
  mp4: "video/mp4",
  mov: "video/quicktime",
  webm: "video/webm",
  json: "application/json",
  txt: "text/plain; charset=utf-8",
  md: "text/markdown; charset=utf-8",
};

function inferContentType(path: string): string {
  const ext = path.slice(path.lastIndexOf(".") + 1).toLowerCase();
  return CONTENT_TYPE_BY_EXT[ext] ?? "application/octet-stream";
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ videoId: string }> },
) {
  const denied = await requireAdminRoute();
  if (denied) return denied;

  const { videoId } = await params;
  const path = request.nextUrl.searchParams.get("path");
  if (!path) {
    return NextResponse.json({ detail: "Missing path" }, { status: 400 });
  }
  if (path.includes("..") || path.startsWith("/")) {
    return NextResponse.json({ detail: "Invalid path" }, { status: 400 });
  }

  const result = await streamRunArtifact(videoId, path);
  if (!result || !result.body) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const headers = new Headers();
  headers.set("Content-Type", result.contentType ?? inferContentType(path));
  if (result.contentLength) {
    headers.set("Content-Length", String(result.contentLength));
  }
  headers.set("Cache-Control", "private, max-age=300");

  return new NextResponse(result.body, { status: 200, headers });
}
