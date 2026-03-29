"use client";

import { useEffect, useRef, useState } from "react";

export default function NewDropdown({
  onConvertVideo,
  onAddChannel,
}: {
  onConvertVideo: () => void;
  onAddChannel: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
      >
        + New
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-52 overflow-hidden rounded-lg border border-stone-200 bg-white shadow-lg">
          <button
            onClick={() => {
              setOpen(false);
              onConvertVideo();
            }}
            className="w-full border-b border-stone-100 px-4 py-3 text-left hover:bg-stone-50"
          >
            <p className="text-sm font-medium text-stone-900">Convert a video</p>
            <p className="mt-0.5 text-xs text-stone-500">Paste a YouTube URL</p>
          </button>
          <button
            onClick={() => {
              setOpen(false);
              onAddChannel();
            }}
            className="w-full px-4 py-3 text-left hover:bg-stone-50"
          >
            <p className="text-sm font-medium text-stone-900">Add a channel</p>
            <p className="mt-0.5 text-xs text-stone-500">Subscribe for new videos</p>
          </button>
        </div>
      )}
    </div>
  );
}
