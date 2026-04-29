import { markdownToHtml } from "@/app/lib/markdown";

export default function Final({ markdown }: { markdown: string | null }) {
  if (!markdown) {
    return (
      <div className="rounded-lg border border-stone-200 bg-stone-50 p-6 text-center text-sm text-stone-500">
        No final essay available — the place_images step has not run.
      </div>
    );
  }

  return (
    <article
      className="max-w-none font-serif text-stone-800 leading-relaxed"
      dangerouslySetInnerHTML={{ __html: markdownToHtml(markdown) }}
    />
  );
}
