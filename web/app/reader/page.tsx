"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { apiJson } from "../lib/api";
import { markdownToHtml } from "../lib/markdown";

interface VideoDetail {
  id: string;
  youtube_video_id: string;
  youtube_url: string;
  video_title: string | null;
  status: string;
  error: string | null;
  essay_md: string | null;
  created_at: string;
}

function ReaderContent() {
  const searchParams = useSearchParams();
  const id = searchParams.get("id");
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    apiJson<VideoDetail>(`/api/videos/${id}`)
      .then(setVideo)
      .catch((err) => setError(err.message));
  }, [id]);

  if (!id) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <p className="text-stone-400">No video ID provided.</p>
        <Link href="/" className="text-sm text-stone-500 hover:text-stone-900">
          &larr; Back to Videos
        </Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <Link href="/" className="text-sm text-stone-500 hover:text-stone-900">
          &larr; Back to Videos
        </Link>
        <p className="mt-4 text-red-600">{error}</p>
      </div>
    );
  }

  if (!video) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <p className="text-stone-400">Loading...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <Link href="/" className="text-sm text-stone-500 hover:text-stone-900">
        &larr; Back to Videos
      </Link>

      <div className="mt-4">
        <p className="text-xs text-stone-400">
          {new Date(video.created_at).toLocaleDateString("en-US", {
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight">
          {video.video_title || "Untitled"}
        </h1>
        <a
          href={video.youtube_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-1 inline-block text-sm text-stone-500 hover:text-stone-900"
        >
          Watch on YouTube &#x2197;
        </a>
      </div>

      {video.status === "done" && video.essay_md ? (
        <article
          className="mt-8 max-w-none font-serif text-stone-800 leading-relaxed"
          dangerouslySetInnerHTML={{ __html: markdownToHtml(video.essay_md) }}
        />
      ) : video.status === "done" && !video.essay_md ? (
        <div className="mt-8 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm text-amber-700">
            Essay file could not be loaded. It may not have been uploaded to storage yet.
          </p>
        </div>
      ) : video.status === "failed" ? (
        <div className="mt-8 rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700">{video.error}</p>
        </div>
      ) : (
        <div className="mt-8 text-center">
          <p className="text-stone-400">
            This video is still being processed...
          </p>
        </div>
      )}
    </div>
  );
}

export default function ReaderPage() {
  return (
    <Suspense fallback={<p className="px-6 py-8 text-stone-400">Loading...</p>}>
      <ReaderContent />
    </Suspense>
  );
}

