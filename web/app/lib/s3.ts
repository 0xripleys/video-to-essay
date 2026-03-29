import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";

const bucket = process.env.S3_BUCKET_NAME;

let client: S3Client | null = null;

function getClient(): S3Client {
  if (!client) {
    client = new S3Client({ region: process.env.AWS_REGION || "us-east-1" });
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
