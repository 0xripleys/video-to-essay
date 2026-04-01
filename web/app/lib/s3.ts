const bucket = process.env.S3_BUCKET_NAME;
const region = process.env.AWS_REGION || "us-east-1";

export async function getEssayFromS3(
  videoId: string,
): Promise<string | null> {
  const paths = [
    `runs/${videoId}/05_place_images/essay_final.md`,
    `runs/${videoId}/03_essay/essay.md`,
  ];
  for (const key of paths) {
    try {
      const url = `https://${bucket}.s3.${region}.amazonaws.com/${key}`;
      const resp = await fetch(url);
      if (resp.ok) return await resp.text();
    } catch {
      continue;
    }
  }
  return null;
}
