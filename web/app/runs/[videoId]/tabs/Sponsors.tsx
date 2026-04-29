function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50 p-6 text-center text-sm text-stone-500">
      {children}
    </div>
  );
}

function formatMmss(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** Parse a leading [MM:SS] timestamp from the start of a paragraph. Handles
 *  the multi-speaker `**Name** [MM:SS]` form too. */
function paragraphTimestamp(paragraph: string): number | null {
  const match = paragraph.match(/(?:\*\*[^*]+\*\*\s*)?\[(\d+):(\d{2})\]/);
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2]);
}

interface SponsorRange {
  start: string;
  end: string;
  reason?: string;
}

function parseRanges(json: string | null): SponsorRange[] {
  if (!json) return [];
  try {
    const parsed = JSON.parse(json);
    if (Array.isArray(parsed)) {
      // Python writes either [[start_sec, end_sec], ...] or [{start, end, reason}, ...]
      return parsed.map((entry: unknown) => {
        if (Array.isArray(entry) && entry.length >= 2) {
          return {
            start: formatMmss(Number(entry[0])),
            end: formatMmss(Number(entry[1])),
          };
        }
        if (entry && typeof entry === "object") {
          const e = entry as Record<string, unknown>;
          return {
            start: String(e.start ?? ""),
            end: String(e.end ?? ""),
            reason: e.reason ? String(e.reason) : undefined,
          };
        }
        return { start: "", end: "" };
      });
    }
  } catch {
    // ignore
  }
  return [];
}

function rangesToSeconds(ranges: SponsorRange[]): [number, number][] {
  const out: [number, number][] = [];
  for (const r of ranges) {
    const sm = r.start.match(/(\d+):(\d{2})/);
    const em = r.end.match(/(\d+):(\d{2})/);
    if (sm && em) {
      out.push([
        Number(sm[1]) * 60 + Number(sm[2]),
        Number(em[1]) * 60 + Number(em[2]),
      ]);
    }
  }
  return out;
}

export default function Sponsors({
  transcript,
  sponsorsJson,
}: {
  transcript: string | null;
  sponsorsJson: string | null;
}) {
  if (!transcript) {
    return <EmptyState>No transcript available — sponsor filter cannot be visualized.</EmptyState>;
  }

  const ranges = parseRanges(sponsorsJson);
  const numericRanges = rangesToSeconds(ranges);

  if (ranges.length === 0) {
    return (
      <EmptyState>
        No sponsor segments detected.
      </EmptyState>
    );
  }

  const paragraphs = transcript.split("\n\n");

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
        <p className="text-xs font-medium uppercase tracking-wide text-amber-700">
          {ranges.length} sponsor segment{ranges.length === 1 ? "" : "s"} detected
        </p>
        <ul className="mt-2 space-y-1 text-sm text-amber-900">
          {ranges.map((r, i) => (
            <li key={i}>
              <span className="font-mono">{r.start} – {r.end}</span>
              {r.reason ? <span className="ml-2 text-amber-700">— {r.reason}</span> : null}
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-lg border border-stone-200 bg-white">
        {paragraphs.map((p, i) => {
          const ts = paragraphTimestamp(p);
          const inSponsor =
            ts !== null && numericRanges.some(([s, e]) => ts >= s && ts <= e);
          return (
            <div
              key={i}
              className={`whitespace-pre-wrap break-words border-b border-stone-100 px-4 py-3 text-sm last:border-0 ${
                inSponsor
                  ? "bg-red-50 text-red-700 line-through decoration-red-300"
                  : "text-stone-800"
              }`}
            >
              {p}
            </div>
          );
        })}
      </div>
    </div>
  );
}
