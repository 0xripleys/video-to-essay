"use client";

import { useMemo, useState } from "react";

interface Classification {
  frame: string;
  timestamp: string;
  category: string;
  value: number;
  description?: string;
}

const SKIP_CATEGORIES = new Set(["talking_head", "transition", "advertisement"]);
const MIN_VALUE = 3;

function rejectionReason(c: Classification): string | null {
  if (SKIP_CATEGORIES.has(c.category)) return `category: ${c.category}`;
  if (c.value < MIN_VALUE) return `low value (${c.value})`;
  return null;
}

const VALUE_COLOR = ["bg-stone-200 text-stone-600", "bg-red-100 text-red-700", "bg-orange-100 text-orange-700", "bg-amber-100 text-amber-700", "bg-lime-100 text-lime-700", "bg-green-100 text-green-700"];

function valueClass(v: number): string {
  return VALUE_COLOR[Math.max(0, Math.min(5, v))] ?? VALUE_COLOR[0];
}

const CATEGORY_COLOR: Record<string, string> = {
  slide: "bg-blue-100 text-blue-700",
  chart: "bg-purple-100 text-purple-700",
  code: "bg-indigo-100 text-indigo-700",
  diagram: "bg-cyan-100 text-cyan-700",
  key_moment: "bg-emerald-100 text-emerald-700",
  talking_head: "bg-stone-100 text-stone-600",
  transition: "bg-stone-100 text-stone-500",
  advertisement: "bg-red-100 text-red-700",
  other: "bg-stone-100 text-stone-600",
};

function frameUrl(videoId: string, frameName: string): string {
  return `/api/runs/${videoId}/files/raw?path=${encodeURIComponent(`04_frames/raw/${frameName}`)}`;
}

export default function Frames({
  videoId,
  classificationsJson,
  keptFrames,
}: {
  videoId: string;
  classificationsJson: string | null;
  keptFrames: string[];
}) {
  const [filter, setFilter] = useState<"all" | "kept" | "rejected">("all");
  const [activeCategories, setActiveCategories] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Classification | null>(null);

  const classifications: Classification[] = useMemo(() => {
    if (!classificationsJson) return [];
    try {
      const parsed = JSON.parse(classificationsJson);
      if (!Array.isArray(parsed)) return [];
      return parsed.map((c: Record<string, unknown>) => ({
        frame: String(c.frame ?? ""),
        timestamp: String(c.timestamp ?? ""),
        category: String(c.category ?? "unknown"),
        value: Number(c.value ?? 0),
        description: c.description ? String(c.description) : undefined,
      }));
    } catch {
      return [];
    }
  }, [classificationsJson]);

  const keptSet = useMemo(() => new Set(keptFrames), [keptFrames]);

  const allCategories = useMemo(() => {
    const s = new Set<string>();
    for (const c of classifications) s.add(c.category);
    return Array.from(s).sort();
  }, [classifications]);

  if (classifications.length === 0) {
    return (
      <div className="rounded-lg border border-stone-200 bg-stone-50 p-6 text-center text-sm text-stone-500">
        No frame classifications available — the frames step has not run.
      </div>
    );
  }

  const visible = classifications.filter((c) => {
    const isKept = keptSet.has(c.frame);
    if (filter === "kept" && !isKept) return false;
    if (filter === "rejected" && isKept) return false;
    if (activeCategories.size > 0 && !activeCategories.has(c.category)) return false;
    return true;
  });

  const toggleCategory = (cat: string) => {
    const next = new Set(activeCategories);
    if (next.has(cat)) next.delete(cat);
    else next.add(cat);
    setActiveCategories(next);
  };

  const keptCount = classifications.filter((c) => keptSet.has(c.frame)).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1">
          {(["all", "kept", "rejected"] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`rounded-full px-3 py-1 text-xs ${
                filter === f
                  ? "bg-stone-900 text-white"
                  : "bg-stone-100 text-stone-600 hover:bg-stone-200"
              }`}
            >
              {f === "all"
                ? `All (${classifications.length})`
                : f === "kept"
                  ? `Kept (${keptCount})`
                  : `Rejected (${classifications.length - keptCount})`}
            </button>
          ))}
        </div>

        <div className="h-4 w-px bg-stone-200" />

        <div className="flex flex-wrap gap-1">
          {allCategories.map((cat) => {
            const active = activeCategories.has(cat);
            return (
              <button
                key={cat}
                type="button"
                onClick={() => toggleCategory(cat)}
                className={`rounded-full px-2.5 py-1 text-[11px] ${
                  active
                    ? "bg-stone-900 text-white"
                    : `${CATEGORY_COLOR[cat] ?? "bg-stone-100 text-stone-600"} hover:opacity-80`
                }`}
              >
                {cat}
              </button>
            );
          })}
          {activeCategories.size > 0 ? (
            <button
              type="button"
              onClick={() => setActiveCategories(new Set())}
              className="rounded-full bg-stone-100 px-2.5 py-1 text-[11px] text-stone-500 hover:bg-stone-200"
            >
              clear
            </button>
          ) : null}
        </div>
      </div>

      <p className="text-xs text-stone-500">
        Showing {visible.length} of {classifications.length} frames.
      </p>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        {visible.map((c) => {
          const isKept = keptSet.has(c.frame);
          const reason = isKept ? null : rejectionReason(c);
          const url = frameUrl(videoId, c.frame);
          return (
            <button
              key={c.frame}
              type="button"
              onClick={() => setExpanded(c)}
              className="overflow-hidden rounded-lg border border-stone-200 bg-white text-left transition-shadow hover:shadow-md"
            >
              <div className="relative aspect-video bg-stone-100">
                <img
                  src={url}
                  alt={c.description ?? c.frame}
                  loading="lazy"
                  className="h-full w-full object-cover"
                />
                <span className="absolute left-1 top-1 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10px] text-white">
                  {c.timestamp}
                </span>
                <span
                  className={`absolute right-1 top-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                    isKept ? "bg-green-600 text-white" : "bg-stone-900/80 text-white"
                  }`}
                >
                  {isKept ? "KEPT" : "REJECTED"}
                </span>
              </div>
              <div className="space-y-1 p-2">
                <div className="flex flex-wrap items-center gap-1">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${CATEGORY_COLOR[c.category] ?? "bg-stone-100 text-stone-600"}`}>
                    {c.category}
                  </span>
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${valueClass(c.value)}`}>
                    v{c.value}
                  </span>
                  {reason ? (
                    <span className="text-[10px] text-stone-500">— {reason}</span>
                  ) : null}
                </div>
                <p className="line-clamp-2 text-[11px] text-stone-600">
                  {c.description ?? ""}
                </p>
              </div>
            </button>
          );
        })}
      </div>

      {expanded ? (
        <button
          type="button"
          aria-label="Close"
          onClick={() => setExpanded(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        >
          <div
            className="max-h-[90vh] max-w-3xl overflow-auto rounded-lg bg-white p-4 text-left"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={frameUrl(videoId, expanded.frame)}
              alt={expanded.description ?? expanded.frame}
              className="max-h-[60vh] w-full rounded object-contain"
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-stone-500">
                {expanded.timestamp} · {expanded.frame}
              </span>
              <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${CATEGORY_COLOR[expanded.category] ?? "bg-stone-100 text-stone-600"}`}>
                {expanded.category}
              </span>
              <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${valueClass(expanded.value)}`}>
                value {expanded.value}
              </span>
              <span
                className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                  keptSet.has(expanded.frame) ? "bg-green-600 text-white" : "bg-stone-900/80 text-white"
                }`}
              >
                {keptSet.has(expanded.frame) ? "KEPT" : "REJECTED"}
              </span>
            </div>
            {expanded.description ? (
              <p className="mt-3 text-sm text-stone-700">{expanded.description}</p>
            ) : null}
          </div>
        </button>
      ) : null}
    </div>
  );
}
