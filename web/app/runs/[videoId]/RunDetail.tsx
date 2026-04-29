"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Overview from "./tabs/Overview";
import Transcript from "./tabs/Transcript";
import Sponsors from "./tabs/Sponsors";
import Essay from "./tabs/Essay";
import Frames from "./tabs/Frames";
import Final from "./tabs/Final";
import RawFiles from "./tabs/RawFiles";

export interface VideoSummary {
  id: string;
  youtube_video_id: string;
  youtube_url: string;
  video_title: string | null;
  channel_name: string | null;
  status: "done" | "failed" | "processing" | "pending_download";
  error: string | null;
  created_at: string;
}

export interface RunFile {
  relativePath: string;
  size: number;
}

export interface RunDetailProps {
  video: VideoSummary;
  artifacts: Record<string, string | null>;
  files: RunFile[];
  keptFrames: string[];
}

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "transcript", label: "Transcript" },
  { id: "sponsors", label: "Sponsors" },
  { id: "essay", label: "Essay" },
  { id: "frames", label: "Frames" },
  { id: "final", label: "Final" },
  { id: "raw", label: "Raw files" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const STATUS_BADGE: Record<VideoSummary["status"], string> = {
  done: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  processing: "bg-amber-100 text-amber-700",
  pending_download: "bg-stone-100 text-stone-600",
};

export default function RunDetail(props: RunDetailProps) {
  const { video } = props;
  const [tab, setTab] = useState<TabId>("overview");

  useEffect(() => {
    const sync = () => {
      const hash = window.location.hash.slice(1) as TabId;
      if (TABS.some((t) => t.id === hash)) setTab(hash);
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  const selectTab = (id: TabId) => {
    setTab(id);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", `#${id}`);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <Link href="/runs" className="text-sm text-stone-500 hover:text-stone-900">
        ← Back to runs
      </Link>

      <header className="mt-4">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-stone-900">
            {video.video_title || "Untitled"}
          </h1>
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_BADGE[video.status]}`}
          >
            {video.status}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-stone-500">
          <a
            href={video.youtube_url}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-stone-900"
          >
            {video.youtube_url} ↗
          </a>
          {video.channel_name ? <span>· {video.channel_name}</span> : null}
          <span>· {new Date(video.created_at).toLocaleString()}</span>
          <span>· <code className="font-mono">{video.youtube_video_id}</code></span>
        </div>
      </header>

      <nav className="mt-6 flex flex-wrap gap-1 border-b border-stone-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => selectTab(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors ${
              tab === t.id
                ? "border-stone-900 text-stone-900"
                : "border-transparent text-stone-500 hover:text-stone-900"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div className="mt-6">
        {tab === "overview" && <Overview video={video} metadataJson={props.artifacts["00_download/metadata.json"]} />}
        {tab === "transcript" && (
          <Transcript
            transcript={props.artifacts["01_transcript/transcript.txt"]}
            speakerMapJson={props.artifacts["01_transcript/speaker_map.json"]}
          />
        )}
        {tab === "sponsors" && (
          <Sponsors
            transcript={props.artifacts["01_transcript/transcript.txt"]}
            sponsorsJson={props.artifacts["02_filter_sponsors/sponsor_segments.json"]}
          />
        )}
        {tab === "essay" && <Essay markdown={props.artifacts["03_essay/essay.md"]} />}
        {tab === "frames" && (
          <Frames
            videoId={video.youtube_video_id}
            classificationsJson={props.artifacts["04_frames/classifications.json"]}
            keptFrames={props.keptFrames}
          />
        )}
        {tab === "final" && <Final markdown={props.artifacts["05_place_images/essay_final.md"]} />}
        {tab === "raw" && (
          <RawFiles
            videoId={video.youtube_video_id}
            files={props.files}
          />
        )}
      </div>
    </div>
  );
}
