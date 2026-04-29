import Link from "next/link";
import { getVideoByYoutubeId, videoStatus } from "@/app/lib/db";
import {
  getRunArtifacts,
  listRunFiles,
} from "@/app/lib/s3";
import RunDetail from "./RunDetail";

const ARTIFACT_PATHS = [
  "00_download/metadata.json",
  "01_transcript/transcript.txt",
  "01_transcript/speaker_map.json",
  "02_filter_sponsors/sponsor_segments.json",
  "03_essay/essay.md",
  "04_frames/classifications.json",
  "05_place_images/essay_final.md",
];

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ videoId: string }>;
}) {
  const { videoId } = await params;

  const video = await getVideoByYoutubeId(videoId);
  if (!video) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <Link
          href="/runs"
          className="text-sm text-stone-500 hover:text-stone-900"
        >
          ← Back to runs
        </Link>
        <h1 className="mt-4 text-xl font-semibold">Video not found</h1>
        <p className="mt-1 text-sm text-stone-500">
          No video with youtube_video_id <code className="font-mono">{videoId}</code> exists in the database.
        </p>
      </div>
    );
  }

  const [artifacts, files] = await Promise.all([
    getRunArtifacts(videoId, ARTIFACT_PATHS),
    listRunFiles(videoId),
  ]);

  const keptFrames = files
    .filter((f) => f.relativePath.startsWith("04_frames/kept/") && f.relativePath.endsWith(".jpg"))
    .map((f) => f.relativePath.split("/").pop()!)
    .filter((name) => name.startsWith("frame_"));

  const status = videoStatus(video);

  return (
    <RunDetail
      video={{
        id: video.id,
        youtube_video_id: video.youtube_video_id,
        youtube_url: video.youtube_url,
        video_title: video.video_title,
        channel_name: video.channel_name,
        status,
        error: video.error,
        created_at: video.created_at,
      }}
      artifacts={artifacts}
      files={files.map((f) => ({
        relativePath: f.relativePath,
        size: f.size,
      }))}
      keptFrames={keptFrames}
    />
  );
}
