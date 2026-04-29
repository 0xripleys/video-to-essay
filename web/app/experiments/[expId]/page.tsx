import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getCellScore,
  getManifest,
  type CellSummary,
} from "@/app/lib/experiments";

interface AggregateRow {
  variant: string;
  slug: string;
  perVideo: Record<string, CellSummary>;
}

const DIMENSIONS = [
  "faithfulness",
  "proportionality",
  "embellishment",
  "hallucination",
  "tone",
] as const;
type Dimension = (typeof DIMENSIONS)[number];

interface DimensionRow {
  variant: string;
  scores: Record<Dimension, number | null>;
}

function bestScore(values: (number | null)[]): number | null {
  const nums = values.filter((v): v is number => typeof v === "number");
  return nums.length ? Math.max(...nums) : null;
}

function scoreClass(score: number | null, best: number | null): string {
  if (score === null) return "text-stone-400";
  if (best === null) return "text-stone-700";
  if (score >= best - 0.3) return "text-green-700 font-semibold";
  if (score < best - 1.0) return "text-red-700";
  return "text-stone-700";
}

function formatCost(cost: number | null): string {
  if (cost === null) return "—";
  return `$${cost.toFixed(4)}`;
}

function formatWall(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

export default async function ExperimentDetailPage({
  params,
}: {
  params: Promise<{ expId: string }>;
}) {
  const { expId } = await params;
  const manifest = await getManifest(expId);
  if (!manifest) notFound();

  // Build (variant × video) aggregate
  const rows: AggregateRow[] = manifest.variants.map((variant) => {
    const slug = manifest.cells.find((c) => c.variant === variant)?.slug ?? variant;
    const perVideo: Record<string, CellSummary> = {};
    for (const cell of manifest.cells.filter((c) => c.variant === variant)) {
      perVideo[cell.video_id] = cell;
    }
    return { variant, slug, perVideo };
  });

  // Best score per video for color-coding
  const bestPerVideo: Record<string, number | null> = {};
  for (const v of manifest.videos) {
    bestPerVideo[v] = bestScore(rows.map((r) => r.perVideo[v]?.score_overall ?? null));
  }

  const showScore = manifest.step === "essay";

  // Per-dimension breakdown (essay step only): fetch each cell's score.json
  // and average per dimension across videos.
  let dimensionRows: DimensionRow[] = [];
  if (showScore) {
    dimensionRows = await Promise.all(
      manifest.variants.map(async (variant) => {
        const cells = manifest.cells.filter(
          (c) => c.variant === variant && c.status === "ok",
        );
        const scores: Record<string, number[]> = Object.fromEntries(
          DIMENSIONS.map((d) => [d, []]),
        );
        await Promise.all(
          cells.map(async (cell) => {
            const score = await getCellScore(
              manifest.exp_id,
              cell.video_id,
              manifest.step,
              cell.slug,
            );
            const dims = (score?.dimensions ?? {}) as Record<
              string,
              { score?: number }
            >;
            for (const d of DIMENSIONS) {
              const v = dims[d]?.score;
              if (typeof v === "number") scores[d].push(v);
            }
          }),
        );
        const averaged = Object.fromEntries(
          DIMENSIONS.map((d) => [
            d,
            scores[d].length === 0
              ? null
              : Math.round(
                  (scores[d].reduce((a, b) => a + b, 0) / scores[d].length) *
                    10,
                ) / 10,
          ]),
        ) as Record<Dimension, number | null>;
        return { variant, scores: averaged };
      }),
    );
  }

  // Best per dimension for color coding
  const bestPerDim: Record<Dimension, number | null> = Object.fromEntries(
    DIMENSIONS.map((d) => [
      d,
      bestScore(dimensionRows.map((r) => r.scores[d])),
    ]),
  ) as Record<Dimension, number | null>;

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <Link
        href="/experiments"
        className="text-sm text-stone-500 hover:text-stone-900"
      >
        ← Experiments
      </Link>

      <h1 className="mt-3 font-mono text-lg text-stone-900">{manifest.exp_id}</h1>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-stone-500 sm:grid-cols-4">
        <div>
          <span className="text-stone-400">Step:</span>{" "}
          <span className="text-stone-700">{manifest.step}</span>
        </div>
        <div>
          <span className="text-stone-400">Videos:</span>{" "}
          <span className="text-stone-700">{manifest.videos.length}</span>
        </div>
        <div>
          <span className="text-stone-400">Cells:</span>{" "}
          <span className="text-stone-700">
            {manifest.ok_count}/{manifest.cells.length} ok
          </span>
        </div>
        <div>
          <span className="text-stone-400">Judge:</span>{" "}
          <span className="font-mono text-xs text-stone-700">{manifest.judge_model}</span>
        </div>
      </div>

      <div className="mt-6 overflow-x-auto rounded-lg border border-stone-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-left text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-2 font-medium">Variant</th>
              {manifest.videos.map((v) => (
                <th key={v} className="px-4 py-2 font-medium">
                  <span className="font-mono text-[11px]">{v}</span>
                </th>
              ))}
              {showScore ? (
                <th className="px-4 py-2 font-medium">avg score</th>
              ) : null}
              <th className="px-4 py-2 font-medium">avg cost</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const scores = manifest.videos
                .map((v) => row.perVideo[v]?.score_overall ?? null)
                .filter((s): s is number => typeof s === "number");
              const avgScore =
                scores.length === 0
                  ? null
                  : Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 10) / 10;

              const costs = manifest.videos
                .map((v) => row.perVideo[v]?.cost_usd ?? null)
                .filter((c): c is number => typeof c === "number");
              const avgCost =
                costs.length === 0
                  ? null
                  : costs.reduce((a, b) => a + b, 0) / costs.length;

              return (
                <tr
                  key={row.variant}
                  className="border-b border-stone-100 last:border-0 align-top"
                >
                  <td className="px-4 py-3">
                    <div className="font-mono text-xs text-stone-700">
                      {row.variant}
                    </div>
                  </td>
                  {manifest.videos.map((v) => {
                    const cell = row.perVideo[v];
                    if (!cell) {
                      return (
                        <td key={v} className="px-4 py-3 text-stone-400">
                          —
                        </td>
                      );
                    }
                    if (cell.status !== "ok") {
                      return (
                        <td key={v} className="px-4 py-3 text-red-700">
                          <Link
                            href={`/experiments/${manifest.exp_id}/${v}`}
                            className="hover:underline"
                            title={cell.status}
                          >
                            failed
                          </Link>
                        </td>
                      );
                    }
                    return (
                      <td key={v} className="px-4 py-3">
                        <Link
                          href={`/experiments/${manifest.exp_id}/${v}`}
                          className="block hover:underline"
                        >
                          {showScore ? (
                            <div
                              className={scoreClass(
                                cell.score_overall,
                                bestPerVideo[v],
                              )}
                            >
                              {cell.score_overall ?? "—"}
                            </div>
                          ) : null}
                          <div className="text-stone-500">
                            {formatCost(cell.cost_usd)}
                          </div>
                          <div className="text-xs text-stone-400">
                            {formatWall(cell.wall_ms)}
                          </div>
                        </Link>
                      </td>
                    );
                  })}
                  {showScore ? (
                    <td className="px-4 py-3 text-stone-700">
                      {avgScore ?? "—"}
                    </td>
                  ) : null}
                  <td className="px-4 py-3 text-stone-500">
                    {avgCost === null ? "—" : `$${avgCost.toFixed(4)}`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {showScore && dimensionRows.length > 0 ? (
        <div className="mt-8">
          <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-stone-500">
            Per-dimension scores{" "}
            <span className="text-stone-400">
              (averaged across {manifest.videos.length} video
              {manifest.videos.length === 1 ? "" : "s"})
            </span>
          </h2>
          <div className="overflow-x-auto rounded-lg border border-stone-200 bg-white">
            <table className="min-w-full text-sm">
              <thead className="border-b border-stone-200 bg-stone-50 text-left text-xs uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="px-4 py-2 font-medium">Variant</th>
                  {DIMENSIONS.map((d) => (
                    <th key={d} className="px-4 py-2 font-medium">
                      {d}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dimensionRows.map((row) => (
                  <tr
                    key={row.variant}
                    className="border-b border-stone-100 last:border-0"
                  >
                    <td className="px-4 py-3">
                      <div className="font-mono text-xs text-stone-700">
                        {row.variant}
                      </div>
                    </td>
                    {DIMENSIONS.map((d) => (
                      <td
                        key={d}
                        className={`px-4 py-3 ${scoreClass(
                          row.scores[d],
                          bestPerDim[d],
                        )}`}
                      >
                        {row.scores[d] ?? "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {manifest.step === "all" && manifest.configs ? (
        <details className="mt-6 rounded-lg border border-stone-200 bg-stone-50 p-4">
          <summary className="cursor-pointer text-sm font-medium text-stone-700">
            Resolved configs
          </summary>
          <pre className="mt-3 overflow-x-auto text-xs text-stone-600">
            {JSON.stringify(manifest.configs, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
