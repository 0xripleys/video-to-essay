/** Simple markdown to HTML — handles the essay output format. */
export function markdownToHtml(md: string): string {
  return md
    .replace(
      /!\[([^\]]*)\]\(([^)]+)\)/g,
      '<img src="$2" alt="$1" class="rounded-lg my-4 max-w-full" />',
    )
    .replace(
      /\[([^\]]+)\]\(([^)]+)\)/g,
      '<a href="$2" class="text-stone-500 hover:text-stone-700 underline" target="_blank" rel="noopener noreferrer">$1</a>',
    )
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\w)\*(.+?)\*(?!\w)/g, "<em>$1</em>")
    .replace(
      /^### (.+)$/gm,
      '<h3 class="text-lg font-bold mt-8 mb-2 font-sans text-stone-900">$1</h3>',
    )
    .replace(
      /^## (.+)$/gm,
      '<h2 class="text-xl font-bold mt-10 mb-3 font-sans text-stone-900">$1</h2>',
    )
    .replace(
      /^# (.+)$/gm,
      '<h1 class="text-2xl font-bold mt-10 mb-4 font-sans text-stone-900">$1</h1>',
    )
    .split("\n\n")
    .map((block) => {
      const trimmed = block.trim();
      if (!trimmed) return "";
      if (trimmed.startsWith("<h") || trimmed.startsWith("<img")) return trimmed;
      return `<p class="mb-4">${trimmed}</p>`;
    })
    .join("\n");
}
