import type { VideoSummary } from "../RunDetail";

interface Metadata {
  title?: string;
  channel?: string;
  uploader?: string;
  duration?: number;
  description?: string;
}

function formatDuration(seconds: number | undefined): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function Overview({
  video,
  metadataJson,
}: {
  video: VideoSummary;
  metadataJson: string | null;
}) {
  let meta: Metadata = {};
  if (metadataJson) {
    try {
      meta = JSON.parse(metadataJson);
    } catch {
      // ignore — show whatever we have
    }
  }

  const rows: [string, React.ReactNode][] = [
    ["Title", meta.title ?? video.video_title ?? "—"],
    ["Channel", meta.channel ?? video.channel_name ?? "—"],
    ["Uploader", meta.uploader ?? "—"],
    ["Duration", formatDuration(meta.duration)],
    ["YouTube ID", <code key="yid" className="font-mono text-xs">{video.youtube_video_id}</code>],
    ["Internal ID", <code key="iid" className="font-mono text-xs">{video.id}</code>],
    ["Status", video.status],
    ["Created", new Date(video.created_at).toLocaleString()],
  ];

  return (
    <div className="space-y-6">
      <div className="overflow-hidden rounded-lg border border-stone-200 bg-white">
        <table className="w-full text-sm">
          <tbody>
            {rows.map(([label, value]) => (
              <tr key={label} className="border-b border-stone-100 last:border-0">
                <td className="w-40 bg-stone-50 px-4 py-2 text-xs font-medium uppercase tracking-wide text-stone-500">
                  {label}
                </td>
                <td className="px-4 py-2 text-stone-800">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {video.error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-red-700">Error</p>
          <pre className="mt-2 whitespace-pre-wrap break-all font-mono text-xs text-red-800">
            {video.error}
          </pre>
        </div>
      ) : null}

      {meta.description ? (
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-stone-500">Description</p>
          <p className="mt-2 whitespace-pre-wrap text-sm text-stone-700">
            {meta.description}
          </p>
        </div>
      ) : null}
    </div>
  );
}
