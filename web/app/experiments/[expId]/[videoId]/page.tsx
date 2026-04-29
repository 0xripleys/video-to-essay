import Link from "next/link";
import { notFound } from "next/navigation";
import {
  fullPipelineStepFilename,
  getCellMeta,
  getCellOutput,
  getCellScore,
  getFullPipelineStepOutput,
  getManifest,
  listLlmCalls,
  primaryOutputFilename,
  type CellSummary,
} from "@/app/lib/experiments";
import SideBySide from "./SideBySide";

const FULL_STEPS = [
  "02_filter_sponsors",
  "03_essay",
  "04_frames",
  "05_place_images",
];

export default async function SideBySidePage({
  params,
  searchParams,
}: {
  params: Promise<{ expId: string; videoId: string }>;
  searchParams: Promise<{ step?: string }>;
}) {
  const { expId, videoId } = await params;
  const sp = await searchParams;
  const manifest = await getManifest(expId);
  if (!manifest) notFound();

  const cells: CellSummary[] = manifest.cells.filter(
    (c) => c.video_id === videoId,
  );
  if (cells.length === 0) notFound();

  const isAll = manifest.step === "all";
  const activeFullStep = isAll
    ? sp.step && FULL_STEPS.includes(sp.step)
      ? sp.step
      : "03_essay"
    : null;

  // Fetch each variant's primary output + meta + score + llm_calls list in parallel
  const panels = await Promise.all(
    cells.map(async (cell) => {
      const [meta, score, llmCalls] = await Promise.all([
        getCellMeta(expId, videoId, manifest.step, cell.slug),
        manifest.step === "essay"
          ? getCellScore(expId, videoId, manifest.step, cell.slug)
          : Promise.resolve(null),
        listLlmCalls(expId, videoId, manifest.step, cell.slug),
      ]);
      let body: string | null = null;
      if (isAll && activeFullStep) {
        body = await getFullPipelineStepOutput(
          expId,
          videoId,
          cell.slug,
          activeFullStep,
          fullPipelineStepFilename(activeFullStep),
        );
      } else {
        body = await getCellOutput(
          expId,
          videoId,
          manifest.step,
          cell.slug,
          primaryOutputFilename(manifest.step),
        );
      }
      return { cell, meta, score, llmCalls, body: body ?? "" };
    }),
  );

  return (
    <div className="px-6 py-6">
      <div className="mx-auto max-w-7xl">
        <div className="flex items-baseline justify-between">
          <Link
            href={`/experiments/${expId}`}
            className="text-sm text-stone-500 hover:text-stone-900"
          >
            ← {manifest.exp_id}
          </Link>
          <div className="font-mono text-sm text-stone-500">{videoId}</div>
        </div>

        {isAll ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {FULL_STEPS.map((s) => {
              const isActive = activeFullStep === s;
              const href = `/experiments/${expId}/${videoId}?step=${s}`;
              return (
                <Link
                  key={s}
                  href={href}
                  className={`rounded-full px-3 py-1 text-xs ${
                    isActive
                      ? "bg-stone-900 text-white"
                      : "bg-stone-100 text-stone-600 hover:bg-stone-200"
                  }`}
                >
                  {s}
                </Link>
              );
            })}
          </div>
        ) : null}
      </div>

      <SideBySide
        panels={panels}
        step={manifest.step}
        expId={expId}
        videoId={videoId}
      />
    </div>
  );
}
