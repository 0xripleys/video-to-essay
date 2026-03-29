import { NextRequest, NextResponse } from "next/server";

const ALLOWED_HOSTS = ["yt3.ggpht.com", "i.ytimg.com"];

export async function GET(request: NextRequest) {
  const url = request.nextUrl.searchParams.get("url");
  if (!url) {
    return NextResponse.json({ detail: "url is required" }, { status: 422 });
  }

  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return NextResponse.json({ detail: "Invalid URL" }, { status: 422 });
  }

  if (!ALLOWED_HOSTS.includes(parsed.hostname)) {
    return NextResponse.json({ detail: "Host not allowed" }, { status: 403 });
  }

  const res = await fetch(url);
  if (!res.ok) {
    return new NextResponse(null, { status: res.status });
  }

  const contentType = res.headers.get("content-type") ?? "image/jpeg";
  const body = await res.arrayBuffer();

  return new NextResponse(body, {
    headers: {
      "Content-Type": contentType,
      "Cache-Control": "public, max-age=86400",
    },
  });
}
