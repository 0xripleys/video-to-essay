"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

interface Job {
  id: string;
  youtube_url: string;
  email: string;
  status: string;
  current_step: string | null;
  error: string | null;
  video_title: string | null;
  created_at: string;
  completed_at: string | null;
}

const STEPS = [
  { key: "download", label: "Downloading video" },
  { key: "transcript", label: "Transcribing audio" },
  { key: "filter_sponsors", label: "Filtering sponsors" },
  { key: "essay", label: "Generating essay" },
  { key: "frames", label: "Extracting frames" },
  { key: "images", label: "Placing images" },
  { key: "email", label: "Sending email" },
];

function stepIndex(step: string | null): number {
  if (!step) return -1;
  return STEPS.findIndex((s) => s.key === step);
}

function StatusContent() {
  const searchParams = useSearchParams();
  const jobId = searchParams.get("id");
  const [job, setJob] = useState<Job | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;

    async function poll() {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (res.status === 404) {
          setNotFound(true);
          return;
        }
        const data = await res.json();
        if (!cancelled) setJob(data);

        if (data.status !== "completed" && data.status !== "failed") {
          setTimeout(poll, 2000);
        }
      } catch {
        if (!cancelled) setTimeout(poll, 5000);
      }
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  if (!jobId) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center px-4">
        <div className="text-center space-y-4">
          <h1 className="text-2xl font-bold">No job ID provided</h1>
          <Link href="/" className="text-stone-500 hover:text-stone-700 underline">
            Go back
          </Link>
        </div>
      </main>
    );
  }

  if (notFound) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center px-4">
        <div className="text-center space-y-4">
          <h1 className="text-2xl font-bold">Job not found</h1>
          <Link href="/" className="text-stone-500 hover:text-stone-700 underline">
            Go back
          </Link>
        </div>
      </main>
    );
  }

  if (!job) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center px-4">
        <p className="text-stone-500">Loading...</p>
      </main>
    );
  }

  const currentIdx = stepIndex(job.current_step);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold tracking-tight">
            {job.status === "completed"
              ? "Essay sent!"
              : job.status === "failed"
                ? "Something went wrong"
                : "Processing your video..."}
          </h1>
          {job.video_title && (
            <p className="mt-1 text-sm text-stone-500">{job.video_title}</p>
          )}
        </div>

        {job.status === "completed" && (
          <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-center">
            <p className="text-green-800">
              Your essay has been sent to <strong>{job.email}</strong>
            </p>
          </div>
        )}

        {job.status === "failed" && job.error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4">
            <p className="text-sm text-red-700">{job.error}</p>
          </div>
        )}

        <div className="space-y-3">
          {STEPS.map((step, i) => {
            let state: "done" | "active" | "pending" = "pending";
            if (job.status === "completed") {
              state = "done";
            } else if (job.status === "failed") {
              state = i < currentIdx ? "done" : i === currentIdx ? "active" : "pending";
            } else if (i < currentIdx) {
              state = "done";
            } else if (i === currentIdx) {
              state = "active";
            }

            return (
              <div key={step.key} className="flex items-center gap-3">
                <div
                  className={`h-3 w-3 rounded-full flex-shrink-0 ${
                    state === "done"
                      ? "bg-green-500"
                      : state === "active"
                        ? "bg-amber-500 animate-pulse"
                        : "bg-stone-200"
                  }`}
                />
                <span
                  className={`text-sm ${
                    state === "pending" ? "text-stone-400" : "text-stone-700"
                  }`}
                >
                  {step.label}
                </span>
              </div>
            );
          })}
        </div>

        <div className="text-center">
          <Link href="/" className="text-sm text-stone-500 hover:text-stone-700 underline">
            Submit another video
          </Link>
        </div>
      </div>
    </main>
  );
}

export default function StatusPage() {
  return (
    <Suspense fallback={<p className="text-stone-500 text-center mt-40">Loading...</p>}>
      <StatusContent />
    </Suspense>
  );
}
