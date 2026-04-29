import { GetObjectCommand, ListObjectsV2Command, S3Client } from "@aws-sdk/client-s3";

const bucket = process.env.S3_BUCKET_NAME;
const region = process.env.AWS_REGION || "us-east-1";

let client: S3Client | null = null;

function getClient(): S3Client {
  if (!client) {
    client = new S3Client({ region });
  }
  return client;
}

export async function getEssayFromS3(
  videoId: string,
): Promise<string | null> {
  const paths = [
    `runs/${videoId}/05_place_images/essay_final.md`,
    `runs/${videoId}/03_essay/essay.md`,
  ];
  const s3 = getClient();
  for (const key of paths) {
    try {
      const resp = await s3.send(
        new GetObjectCommand({ Bucket: bucket, Key: key }),
      );
      return (await resp.Body?.transformToString("utf-8")) ?? null;
    } catch {
      continue;
    }
  }
  return null;
}

/** Fetch a single text artifact from a run. Returns null if missing. */
export async function getRunArtifact(
  videoId: string,
  relativePath: string,
): Promise<string | null> {
  const s3 = getClient();
  const key = `runs/${videoId}/${relativePath}`;
  try {
    const resp = await s3.send(
      new GetObjectCommand({ Bucket: bucket, Key: key }),
    );
    return (await resp.Body?.transformToString("utf-8")) ?? null;
  } catch {
    return null;
  }
}

/** Parallel fetch of multiple artifacts. Missing files come back as null. */
export async function getRunArtifacts(
  videoId: string,
  relativePaths: string[],
): Promise<Record<string, string | null>> {
  const entries = await Promise.all(
    relativePaths.map(async (p) => [p, await getRunArtifact(videoId, p)] as const),
  );
  return Object.fromEntries(entries);
}

export interface S3FileEntry {
  key: string;        // full S3 key, e.g. "runs/abc/01_transcript/transcript.txt"
  relativePath: string; // path relative to runs/<videoId>/
  size: number;
  lastModified: Date | null;
}

/** List all files under runs/<videoId>/. */
export async function listRunFiles(videoId: string): Promise<S3FileEntry[]> {
  const s3 = getClient();
  const prefix = `runs/${videoId}/`;
  const out: S3FileEntry[] = [];
  let continuationToken: string | undefined;
  do {
    const resp = await s3.send(
      new ListObjectsV2Command({
        Bucket: bucket,
        Prefix: prefix,
        ContinuationToken: continuationToken,
      }),
    );
    for (const obj of resp.Contents ?? []) {
      if (!obj.Key) continue;
      out.push({
        key: obj.Key,
        relativePath: obj.Key.slice(prefix.length),
        size: obj.Size ?? 0,
        lastModified: obj.LastModified ?? null,
      });
    }
    continuationToken = resp.NextContinuationToken;
  } while (continuationToken);
  return out;
}

/** URL the browser uses to fetch a run artifact. Routes through the Next.js
 *  API which has S3 credentials — the S3 bucket itself is not public. */
export function getPublicUrl(videoId: string, relativePath: string): string {
  return `/api/runs/${videoId}/files/raw?path=${encodeURIComponent(relativePath)}`;
}

/** Stream a single artifact's raw bytes (used by the streaming API route). */
export async function streamRunArtifact(
  videoId: string,
  relativePath: string,
): Promise<{ body: ReadableStream | null; contentType: string | null; contentLength: number | null } | null> {
  const s3 = getClient();
  const key = `runs/${videoId}/${relativePath}`;
  try {
    const resp = await s3.send(
      new GetObjectCommand({ Bucket: bucket, Key: key }),
    );
    return {
      body: (resp.Body as ReadableStream | undefined) ?? null,
      contentType: resp.ContentType ?? null,
      contentLength: resp.ContentLength ?? null,
    };
  } catch {
    return null;
  }
}
