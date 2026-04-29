import { NextRequest, NextResponse } from "next/server";
import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import fs from "node:fs";
import path from "node:path";
import { requireAdminRoute } from "@/app/lib/admin";

const bucket = process.env.S3_BUCKET_NAME;
const region = process.env.AWS_REGION || "us-east-1";

let client: S3Client | null = null;
function getClient(): S3Client {
  if (!client) client = new S3Client({ region });
  return client;
}

function getLocalBase(): string | null {
  for (const p of [
    path.resolve(process.cwd(), "..", "experiments"),
    path.resolve(process.cwd(), "experiments"),
  ]) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ expId: string }> },
) {
  const denied = await requireAdminRoute();
  if (denied) return denied;

  const { expId } = await params;
  const rel = request.nextUrl.searchParams.get("path");
  if (!rel) {
    return NextResponse.json({ detail: "Missing path" }, { status: 400 });
  }
  if (rel.includes("..") || rel.startsWith("/")) {
    return NextResponse.json({ detail: "Invalid path" }, { status: 400 });
  }

  // Try S3 first
  if (bucket) {
    try {
      const resp = await getClient().send(
        new GetObjectCommand({
          Bucket: bucket,
          Key: `experiments/${expId}/${rel}`,
        }),
      );
      const text = (await resp.Body?.transformToString("utf-8")) ?? "";
      return NextResponse.json({ text });
    } catch {
      // fall through to local
    }
  }

  // Local fallback
  const base = getLocalBase();
  if (base) {
    const full = path.join(base, expId, rel);
    if (fs.existsSync(full)) {
      const text = fs.readFileSync(full, "utf-8");
      return NextResponse.json({ text });
    }
  }

  return NextResponse.json({ detail: "Not found" }, { status: 404 });
}
