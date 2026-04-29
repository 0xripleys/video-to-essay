import Link from "next/link";
import { getVideoByYoutubeId, videoStatus } from "@/app/lib/db";
import {
  getRunArtifacts,
  listRunFiles,
} from "@/app/lib/s3";
import { listExpIds, listManifests } from "@/app/lib/experiments";
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

  const [artifacts, files, expIds] = await Promise.all([
    getRunArtifacts(videoId, ARTIFACT_PATHS),
    listRunFiles(videoId),
    listExpIds(),
  ]);

  const allManifests = await listManifests(expIds);
  const matchingExperiments = allManifests.filter((m) =>
    m.videos.includes(videoId),
  );

  const keptFrames = files
    .filter((f) => f.relativePath.startsWith("04_frames/kept/") && f.relativePath.endsWith(".jpg"))
    .map((f) => f.relativePath.split("/").pop()!)
    .filter((name) => name.startsWith("frame_"));

  const status = videoStatus(video);

  return (
    <>
      {matchingExperiments.length > 0 ? (
        <div className="mx-auto max-w-6xl px-6 pt-6">
          <div className="rounded-lg border border-stone-200 bg-stone-50 px-4 py-3 text-sm">
            <div className="text-xs font-medium uppercase tracking-wide text-stone-500">
              Appears in experiments
            </div>
            <ul className="mt-2 space-y-1">
              {matchingExperiments.map((m) => (
                <li key={m.exp_id}>
                  <Link
                    href={`/experiments/${m.exp_id}/${videoId}`}
                    className="font-mono text-xs text-stone-700 hover:underline"
                  >
                    {m.exp_id}
                  </Link>
                  <span className="ml-2 text-xs text-stone-500">
                    {m.step} · {m.variants.join(", ")}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
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
    </>
  );
}
