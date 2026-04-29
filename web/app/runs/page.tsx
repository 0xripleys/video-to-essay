import Link from "next/link";
import { listAllVideos, videoStatus, type VideoStatus } from "@/app/lib/db";
import RunsListControls from "./RunsListControls";

const PAGE_SIZE = 50;

const STATUS_FILTERS: { label: string; value: VideoStatus | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Done", value: "done" },
  { label: "Failed", value: "failed" },
  { label: "Processing", value: "processing" },
];

const STATUS_BADGE_CLASS: Record<VideoStatus, string> = {
  done: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  processing: "bg-amber-100 text-amber-700",
  pending_download: "bg-stone-100 text-stone-600",
};

function formatRelative(date: string): string {
  const d = new Date(date);
  const ms = Date.now() - d.getTime();
  const days = Math.floor(ms / 86_400_000);
  if (days < 1) return "today";
  if (days < 2) return "yesterday";
  if (days < 30) return `${days}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default async function RunsListPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; offset?: string }>;
}) {
  const params = await searchParams;
  const status = (params.status as VideoStatus | "all") ?? "all";
  const offset = Number(params.offset ?? 0);

  const videos = await listAllVideos({ status, limit: PAGE_SIZE, offset });

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="text-2xl font-bold tracking-tight text-stone-900">Runs</h1>
      <p className="mt-1 text-sm text-stone-500">
        Inspect pipeline artifacts for any video.
      </p>

      <div className="mt-6">
        <RunsListControls />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {STATUS_FILTERS.map((f) => {
          const isActive = (status ?? "all") === f.value;
          const href = f.value === "all" ? "/runs" : `/runs?status=${f.value}`;
          return (
            <Link
              key={f.value}
              href={href}
              className={`rounded-full px-3 py-1 text-xs ${
                isActive
                  ? "bg-stone-900 text-white"
                  : "bg-stone-100 text-stone-600 hover:bg-stone-200"
              }`}
            >
              {f.label}
            </Link>
          );
        })}
      </div>

      <div className="mt-6 overflow-hidden rounded-lg border border-stone-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-left text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-2 font-medium">Title</th>
              <th className="px-4 py-2 font-medium">Channel</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Created</th>
            </tr>
          </thead>
          <tbody>
            {videos.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-12 text-center text-stone-400">
                  No runs found.
                </td>
              </tr>
            ) : (
              videos.map((v) => {
                const s = videoStatus(v);
                return (
                  <tr
                    key={v.id}
                    className="border-b border-stone-100 last:border-0 hover:bg-stone-50"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/runs/${v.youtube_video_id}`}
                        className="font-medium text-stone-900 hover:underline"
                      >
                        {v.video_title || (
                          <span className="text-stone-400">Untitled</span>
                        )}
                      </Link>
                      <div className="mt-0.5 font-mono text-[11px] text-stone-400">
                        {v.youtube_video_id}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-stone-600">
                      {v.channel_name ?? <span className="text-stone-400">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_BADGE_CLASS[s]}`}
                      >
                        {s}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-stone-500">
                      {formatRelative(v.created_at)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex justify-between text-sm text-stone-500">
        {offset > 0 ? (
          <Link
            href={`/runs?${new URLSearchParams({
              ...(status !== "all" ? { status } : {}),
              offset: String(Math.max(0, offset - PAGE_SIZE)),
            }).toString()}`}
            className="hover:text-stone-900"
          >
            ← Previous
          </Link>
        ) : (
          <span />
        )}
        {videos.length === PAGE_SIZE ? (
          <Link
            href={`/runs?${new URLSearchParams({
              ...(status !== "all" ? { status } : {}),
              offset: String(offset + PAGE_SIZE),
            }).toString()}`}
            className="hover:text-stone-900"
          >
            Next →
          </Link>
        ) : (
          <span />
        )}
      </div>
    </div>
  );
}
