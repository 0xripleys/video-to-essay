import Link from "next/link";
import { listExpIds, listManifests, type Manifest } from "@/app/lib/experiments";

function formatRelative(date: string): string {
  const d = new Date(date);
  const ms = Date.now() - d.getTime();
  const days = Math.floor(ms / 86_400_000);
  if (days < 1) return "today";
  if (days < 2) return "yesterday";
  if (days < 30) return `${days}d ago`;
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default async function ExperimentsListPage() {
  const expIds = await listExpIds();
  const manifests = await listManifests(expIds);

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-stone-900">
            Experiments
          </h1>
          <p className="mt-1 text-sm text-stone-500">
            Per-step model A/B sweeps. List ordered newest first.
          </p>
        </div>
        <Link
          href="/runs"
          className="text-sm text-stone-500 hover:text-stone-900"
        >
          Runs →
        </Link>
      </div>

      <div className="mt-6 overflow-hidden rounded-lg border border-stone-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-left text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-2 font-medium">When</th>
              <th className="px-4 py-2 font-medium">Step</th>
              <th className="px-4 py-2 font-medium">Variants</th>
              <th className="px-4 py-2 font-medium">Videos</th>
              <th className="px-4 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {manifests.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-4 py-12 text-center text-stone-400"
                >
                  No experiments yet. Run{" "}
                  <code className="font-mono text-stone-500">
                    video-to-essay experiment …
                  </code>{" "}
                  to start one.
                </td>
              </tr>
            ) : (
              manifests.map((m: Manifest) => {
                const total = m.cells.length;
                const ok = m.ok_count;
                const fail = m.fail_count;
                return (
                  <tr
                    key={m.exp_id}
                    className="border-b border-stone-100 last:border-0 hover:bg-stone-50"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/experiments/${m.exp_id}`}
                        className="font-medium text-stone-900 hover:underline"
                      >
                        {formatRelative(m.started_at)}
                      </Link>
                      <div className="mt-0.5 font-mono text-[11px] text-stone-400">
                        {m.exp_id}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-stone-600">{m.step}</td>
                    <td className="px-4 py-3 text-stone-600">
                      {m.variants.slice(0, 3).join(", ")}
                      {m.variants.length > 3 ? ` +${m.variants.length - 3}` : ""}
                    </td>
                    <td className="px-4 py-3 text-stone-500">
                      {m.videos.length}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          fail === 0
                            ? "bg-green-100 text-green-700"
                            : ok === 0
                              ? "bg-red-100 text-red-700"
                              : "bg-amber-100 text-amber-700"
                        }`}
                      >
                        {ok}/{total} ok
                        {fail > 0 ? ` (${fail} failed)` : ""}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
