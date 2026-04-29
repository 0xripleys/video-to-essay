function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50 p-6 text-center text-sm text-stone-500">
      {children}
    </div>
  );
}

export default function Transcript({
  transcript,
  speakerMapJson,
}: {
  transcript: string | null;
  speakerMapJson: string | null;
}) {
  if (!transcript) {
    return <EmptyState>No transcript available — the transcript step has not run.</EmptyState>;
  }

  let speakerMap: Record<string, string> | null = null;
  if (speakerMapJson) {
    try {
      speakerMap = JSON.parse(speakerMapJson);
    } catch {
      speakerMap = null;
    }
  }

  return (
    <div className="space-y-4">
      {speakerMap && Object.keys(speakerMap).length > 0 ? (
        <div className="rounded-lg border border-stone-200 bg-stone-50 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-stone-500">Speaker map</p>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-stone-700">
            {Object.entries(speakerMap).map(([id, name]) => (
              <li key={id}>
                <span className="font-mono text-xs text-stone-400">{id}</span>{" "}
                <span className="font-medium">{name}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <pre className="whitespace-pre-wrap break-words rounded-lg border border-stone-200 bg-white px-4 py-4 text-sm leading-relaxed text-stone-800">
        {transcript}
      </pre>
    </div>
  );
}
