"use client";

import { useMemo, useState } from "react";
import type { RunFile } from "../RunDetail";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

interface FileContent {
  text: string | null;
  contentType: string | null;
  url: string;
  size: number;
}

export default function RawFiles({
  videoId,
  files,
}: {
  videoId: string;
  files: RunFile[];
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<FileContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const out: Record<string, RunFile[]> = {};
    for (const f of files) {
      const step = f.relativePath.split("/")[0] || "(root)";
      (out[step] ??= []).push(f);
    }
    for (const step of Object.keys(out)) {
      out[step].sort((a, b) => a.relativePath.localeCompare(b.relativePath));
    }
    return out;
  }, [files]);

  const select = async (path: string) => {
    setSelected(path);
    setError(null);
    setContent(null);
    setLoading(true);
    try {
      const resp = await fetch(
        `/api/runs/${videoId}/files?path=${encodeURIComponent(path)}`,
      );
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${resp.status}`);
      }
      const data = (await resp.json()) as FileContent;
      setContent(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid gap-4 md:grid-cols-[260px_1fr]">
      <aside className="rounded-lg border border-stone-200 bg-white">
        {Object.keys(grouped).length === 0 ? (
          <p className="p-4 text-sm text-stone-400">No files in S3.</p>
        ) : (
          Object.entries(grouped)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([step, items]) => (
              <div key={step} className="border-b border-stone-100 last:border-0">
                <p className="bg-stone-50 px-3 py-1.5 font-mono text-[11px] uppercase tracking-wide text-stone-500">
                  {step}
                </p>
                <ul>
                  {items.map((f) => {
                    const name = f.relativePath.slice(step.length + 1);
                    return (
                      <li key={f.relativePath}>
                        <button
                          type="button"
                          onClick={() => select(f.relativePath)}
                          className={`flex w-full justify-between px-3 py-1.5 text-left text-xs hover:bg-stone-50 ${
                            selected === f.relativePath ? "bg-stone-100 font-medium" : ""
                          }`}
                        >
                          <span className="truncate font-mono text-stone-700">
                            {name || f.relativePath}
                          </span>
                          <span className="ml-2 shrink-0 text-stone-400">
                            {formatSize(f.size)}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
        )}
      </aside>

      <section className="min-h-[300px] rounded-lg border border-stone-200 bg-white p-4">
        {!selected ? (
          <p className="text-sm text-stone-400">Select a file to view its contents.</p>
        ) : loading ? (
          <p className="text-sm text-stone-500">Loading…</p>
        ) : error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : content ? (
          <FilePreview path={selected} content={content} />
        ) : null}
      </section>
    </div>
  );
}

function FilePreview({ path, content }: { path: string; content: FileContent }) {
  const lower = path.toLowerCase();
  const isImage = /\.(jpe?g|png|gif|webp)$/.test(lower);
  const isAudio = /\.(mp3|wav|m4a|ogg)$/.test(lower);
  const isVideo = /\.(mp4|mov|webm|mkv)$/.test(lower);
  const isJson = lower.endsWith(".json") && content.text !== null;

  let body: React.ReactNode;
  if (isImage) {
    body = <img src={content.url} alt={path} className="max-w-full rounded" />;
  } else if (isAudio) {
    body = <audio src={content.url} controls className="w-full" />;
  } else if (isVideo) {
    body = <video src={content.url} controls className="max-w-full rounded" />;
  } else if (isJson) {
    let pretty = content.text!;
    try {
      pretty = JSON.stringify(JSON.parse(content.text!), null, 2);
    } catch {
      // leave as-is
    }
    body = (
      <pre className="overflow-auto whitespace-pre-wrap break-words rounded bg-stone-50 p-3 font-mono text-xs text-stone-800">
        {pretty}
      </pre>
    );
  } else if (content.text !== null) {
    body = (
      <pre className="overflow-auto whitespace-pre-wrap break-words rounded bg-stone-50 p-3 font-mono text-xs text-stone-800">
        {content.text}
      </pre>
    );
  } else {
    body = (
      <p className="text-sm text-stone-500">
        Binary file ({formatSize(content.size)}).{" "}
        <a href={content.url} target="_blank" rel="noopener noreferrer" className="text-stone-700 underline">
          Open in new tab
        </a>
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="font-mono text-xs text-stone-500">{path}</p>
        <a
          href={content.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-stone-500 hover:text-stone-900"
        >
          Open ↗
        </a>
      </div>
      {body}
    </div>
  );
}
