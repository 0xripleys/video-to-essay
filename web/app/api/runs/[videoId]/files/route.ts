import { NextRequest, NextResponse } from "next/server";
import { requireAdminRoute } from "@/app/lib/admin";
import { getPublicUrl, getRunArtifact, listRunFiles } from "@/app/lib/s3";

const TEXT_EXTENSIONS = new Set([".txt", ".md", ".json", ".log", ".csv"]);

function isTextPath(path: string): boolean {
  const dotIdx = path.lastIndexOf(".");
  if (dotIdx < 0) return false;
  return TEXT_EXTENSIONS.has(path.slice(dotIdx).toLowerCase());
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
    const files = await listRunFiles(videoId);
    return NextResponse.json({ files });
  }

  if (path.includes("..") || path.startsWith("/")) {
    return NextResponse.json({ detail: "Invalid path" }, { status: 400 });
  }

  const url = getPublicUrl(videoId, path);
  const files = await listRunFiles(videoId);
  const file = files.find((f) => f.relativePath === path);
  if (!file) {
    return NextResponse.json({ detail: "File not found" }, { status: 404 });
  }

  const text = isTextPath(path) ? await getRunArtifact(videoId, path) : null;

  return NextResponse.json({
    text,
    contentType: null,
    url,
    size: file.size,
  });
}
