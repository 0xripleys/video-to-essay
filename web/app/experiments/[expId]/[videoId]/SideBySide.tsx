"use client";

import { useEffect, useRef, useState } from "react";
import { markdownToHtml } from "@/app/lib/markdown";
import type { CellSummary } from "@/app/lib/experiments";

interface Panel {
  cell: CellSummary;
  meta: Record<string, unknown> | null;
  score: Record<string, unknown> | null;
  llmCalls: string[];
  body: string;
}

interface DimensionResult {
  score?: number;
  rationale?: string;
  reasoning?: string;
  violations?: Array<{
    essay_quote?: string;
    transcript_evidence?: string;
    explanation?: string;
  }>;
}

const DIMENSIONS = [
  "faithfulness",
  "proportionality",
  "embellishment",
  "hallucination",
  "tone",
] as const;

function formatCost(cost: number | null): string {
  if (cost === null) return "—";
  return `$${cost.toFixed(4)}`;
}

function formatWall(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

export default function SideBySide({
  panels,
  step,
  expId,
  videoId,
}: {
  panels: Panel[];
  step: string;
  expId: string;
  videoId: string;
}) {
  const refs = useRef<(HTMLDivElement | null)[]>([]);
  const syncing = useRef(false);

  useEffect(() => {
    function onScroll(idx: number) {
      return () => {
        if (syncing.current) return;
        const src = refs.current[idx];
        if (!src) return;
        syncing.current = true;
        const ratio =
          src.scrollHeight - src.clientHeight === 0
            ? 0
            : src.scrollTop / (src.scrollHeight - src.clientHeight);
        for (let i = 0; i < refs.current.length; i++) {
          if (i === idx) continue;
          const el = refs.current[i];
          if (!el) continue;
          el.scrollTop = ratio * (el.scrollHeight - el.clientHeight);
        }
        requestAnimationFrame(() => {
          syncing.current = false;
        });
      };
    }

    const handlers = panels.map((_, i) => onScroll(i));
    refs.current.forEach((el, i) => {
      el?.addEventListener("scroll", handlers[i]);
    });
    return () => {
      refs.current.forEach((el, i) => {
        el?.removeEventListener("scroll", handlers[i]);
      });
    };
  }, [panels]);

  const showScore = step === "essay";

  return (
    <div
      className="mt-6 grid gap-4"
      style={{
        gridTemplateColumns: `repeat(${panels.length}, minmax(0, 1fr))`,
      }}
    >
      {panels.map((p, i) => (
        <div
          key={p.cell.slug}
          className="overflow-hidden rounded-lg border border-stone-200 bg-white"
        >
          <header className="border-b border-stone-200 bg-stone-50 px-4 py-3">
            <div className="font-mono text-xs text-stone-700">
              {p.cell.variant}
            </div>
            <div className="mt-1 flex flex-wrap gap-4 text-xs text-stone-500">
              {showScore ? (
                <span>
                  score{" "}
                  <strong className="text-stone-700">
                    {p.cell.score_overall ?? "—"}
                  </strong>
                </span>
              ) : null}
              <span>cost {formatCost(p.cell.cost_usd)}</span>
              <span>wall {formatWall(p.cell.wall_ms)}</span>
              <span
                className={`rounded-full px-2 py-0.5 ${
                  p.cell.status === "ok"
                    ? "bg-green-100 text-green-700"
                    : "bg-red-100 text-red-700"
                }`}
              >
                {p.cell.status === "ok" ? "ok" : "failed"}
              </span>
            </div>
          </header>
          <div
            ref={(el) => {
              refs.current[i] = el;
            }}
            className="prose prose-stone max-h-[60vh] overflow-y-auto px-6 py-4 text-sm leading-relaxed text-stone-800"
            dangerouslySetInnerHTML={{
              __html: p.body
                ? markdownToHtml(p.body)
                : '<p class="italic text-stone-400">No output (cell failed or step has no text artifact).</p>',
            }}
          />
          <PanelDetails
            panel={p}
            showScore={showScore}
            expId={expId}
            videoId={videoId}
            step={step}
          />
        </div>
      ))}
    </div>
  );
}

function PanelDetails({
  panel,
  showScore,
  expId,
  videoId,
  step,
}: {
  panel: Panel;
  showScore: boolean;
  expId: string;
  videoId: string;
  step: string;
}) {
  const dims = (panel.score?.dimensions ?? {}) as Record<
    string,
    DimensionResult
  >;
  const status =
    typeof panel.cell.status === "string" ? panel.cell.status : "ok";

  return (
    <div className="border-t border-stone-200">
      {showScore && Object.keys(dims).length > 0 ? (
        <details className="border-b border-stone-200 px-4 py-3">
          <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-stone-500 hover:text-stone-900">
            Score breakdown
          </summary>
          <div className="mt-3 space-y-3 text-sm">
            {DIMENSIONS.map((d) => {
              const r = dims[d];
              if (!r) return null;
              return (
                <div key={d} className="rounded border border-stone-100 p-3">
                  <div className="flex items-baseline justify-between">
                    <span className="text-xs font-medium uppercase tracking-wide text-stone-500">
                      {d}
                    </span>
                    <span className="font-mono text-stone-800">
                      {r.score ?? "—"}/10
                    </span>
                  </div>
                  {r.rationale ? (
                    <p className="mt-1 text-stone-700">{r.rationale}</p>
                  ) : null}
                  {r.violations && r.violations.length > 0 ? (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs text-red-700 hover:text-red-900">
                        {r.violations.length} violation
                        {r.violations.length === 1 ? "" : "s"}
                      </summary>
                      <ul className="mt-2 space-y-2 text-xs text-stone-600">
                        {r.violations.map((v, idx) => (
                          <li
                            key={idx}
                            className="rounded bg-stone-50 px-2 py-1"
                          >
                            <div className="text-stone-800">
                              {v.explanation}
                            </div>
                            {v.essay_quote ? (
                              <div className="mt-1 italic">
                                essay: “{v.essay_quote}”
                              </div>
                            ) : null}
                            {v.transcript_evidence ? (
                              <div className="mt-1 italic text-stone-500">
                                transcript: “{v.transcript_evidence}”
                              </div>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </div>
              );
            })}
          </div>
        </details>
      ) : null}

      <details className="border-b border-stone-200 px-4 py-3">
        <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-stone-500 hover:text-stone-900">
          meta.json
        </summary>
        <pre className="mt-3 overflow-x-auto rounded bg-stone-50 p-3 text-xs text-stone-700">
          {JSON.stringify(panel.meta, null, 2)}
        </pre>
        {status !== "ok" ? (
          <div className="mt-2 rounded bg-red-50 p-2 text-xs text-red-700">
            {status}
          </div>
        ) : null}
      </details>

      <LlmCallsList
        files={panel.llmCalls}
        expId={expId}
        videoId={videoId}
        step={step}
        slug={panel.cell.slug}
      />
    </div>
  );
}

function LlmCallsList({
  files,
  expId,
  videoId,
  step,
  slug,
}: {
  files: string[];
  expId: string;
  videoId: string;
  step: string;
  slug: string;
}) {
  if (files.length === 0) {
    return (
      <div className="px-4 py-3 text-xs text-stone-400">
        No llm_calls/ files for this cell.
      </div>
    );
  }
  return (
    <details className="px-4 py-3">
      <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-stone-500 hover:text-stone-900">
        LLM calls ({files.length})
      </summary>
      <ul className="mt-3 space-y-2">
        {files.map((file) => (
          <LlmCallItem
            key={file}
            file={file}
            path={`${videoId}/${step}/${slug}/llm_calls/${file}`}
            expId={expId}
          />
        ))}
      </ul>
    </details>
  );
}

function LlmCallItem({
  file,
  path,
  expId,
}: {
  file: string;
  path: string;
  expId: string;
}) {
  const [body, setBody] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (body !== null || loading) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(
        `/api/experiments/${expId}/files?path=${encodeURIComponent(path)}`,
      );
      if (!resp.ok) {
        setError(`HTTP ${resp.status}`);
        return;
      }
      const json = (await resp.json()) as { text?: string };
      setBody(json.text ?? "");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  // Parse the task name from the filename (e.g. "essay_multi_1234.json" → "essay_multi")
  const task = file.replace(/_\d+\.json$/, "");

  return (
    <li className="rounded border border-stone-100">
      <details onToggle={(e) => (e.currentTarget.open ? load() : undefined)}>
        <summary className="cursor-pointer px-3 py-2 text-xs hover:bg-stone-50">
          <span className="font-mono text-stone-700">{task}</span>
          <span className="ml-2 font-mono text-stone-400">{file}</span>
        </summary>
        <div className="border-t border-stone-100 px-3 py-2">
          {loading ? (
            <div className="text-xs text-stone-400">loading…</div>
          ) : error ? (
            <div className="text-xs text-red-700">{error}</div>
          ) : body !== null ? (
            <pre className="max-h-[40vh] overflow-auto whitespace-pre-wrap break-all text-[11px] leading-relaxed text-stone-700">
              {pretty(body)}
            </pre>
          ) : null}
        </div>
      </details>
    </li>
  );
}

function pretty(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}
