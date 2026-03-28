"use client";

export default function Landing() {
  return (
    <div className="flex min-h-screen flex-col bg-stone-50">
      {/* Nav */}
      <nav className="flex items-center justify-between border-b border-stone-200/60 px-8 py-5">
        <a href="/" className="text-[15px] font-semibold tracking-tight text-stone-900">
          Surat
        </a>
        <a
          href="/api/auth/login"
          className="text-sm text-stone-500 transition-colors hover:text-stone-900"
        >
          Sign in
        </a>
      </nav>

      {/* Hero */}
      <div className="flex flex-1 items-center justify-center px-8">
        <div className="flex w-full max-w-4xl items-center gap-16">
          {/* Left: copy */}
          <div className="max-w-md flex-1">
            <h1
              className="text-[2.5rem] leading-[1.1] font-medium tracking-tight text-stone-900"
              style={{ fontFamily: "'Georgia', 'Times New Roman', serif" }}
            >
              YouTube videos,
              <br />
              as illustrated essays
            </h1>
            <p className="mt-4 text-[15px] leading-relaxed text-stone-500">
              Paste a link. Get a beautifully written essay with key frames
              extracted and placed automatically, delivered to your inbox.
            </p>
            <a
              href="/api/auth/login"
              className="mt-7 inline-flex items-center gap-2 rounded-lg bg-stone-900 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-stone-800"
            >
              Get started
              <svg
                width="14"
                height="14"
                viewBox="0 0 16 16"
                fill="none"
                className="opacity-70"
              >
                <path
                  d="M3 8h10M9 4l4 4-4 4"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </a>
          </div>

          {/* Right: before/after */}
          <div className="hidden flex-shrink-0 items-center gap-4 lg:flex">
            {/* Video panel */}
            <div className="w-[180px] overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm">
              <div className="border-b border-stone-100 px-3 py-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-stone-400">
                  Video
                </span>
              </div>
              <div className="p-3">
                {/* Thumbnail */}
                <div className="flex h-[80px] items-center justify-center rounded-md bg-gradient-to-br from-stone-100 to-stone-200">
                  <svg
                    width="28"
                    height="28"
                    viewBox="0 0 24 24"
                    fill="none"
                    className="text-stone-400"
                  >
                    <path
                      d="M8 5.14v13.72a1 1 0 001.5.86l11-6.86a1 1 0 000-1.72l-11-6.86a1 1 0 00-1.5.86z"
                      fill="currentColor"
                      opacity="0.5"
                    />
                  </svg>
                </div>
                {/* Skeleton transcript lines */}
                <div className="mt-3 space-y-2">
                  <div className="h-1.5 w-full rounded-full bg-stone-100" />
                  <div className="h-1.5 w-[85%] rounded-full bg-stone-100" />
                  <div className="h-1.5 w-[92%] rounded-full bg-stone-100" />
                  <div className="h-1.5 w-[70%] rounded-full bg-stone-100" />
                </div>
              </div>
            </div>

            {/* Arrow */}
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              className="flex-shrink-0 text-stone-300"
            >
              <path
                d="M5 12h14M13 6l6 6-6 6"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>

            {/* Essay panel */}
            <div className="w-[180px] overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm">
              <div className="border-b border-stone-100 px-3 py-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-stone-400">
                  Essay
                </span>
              </div>
              <div className="p-3">
                {/* Title */}
                <div
                  className="text-[11px] font-semibold leading-tight text-stone-800"
                  style={{ fontFamily: "'Georgia', serif" }}
                >
                  How Transformers
                  <br />
                  Changed AI
                </div>
                {/* Skeleton text */}
                <div className="mt-2 space-y-1.5">
                  <div className="h-1.5 w-full rounded-full bg-stone-100" />
                  <div className="h-1.5 w-[88%] rounded-full bg-stone-100" />
                </div>
                {/* Image placeholder */}
                <div className="mt-2.5 h-[36px] rounded-md bg-gradient-to-br from-stone-100 to-stone-150 ring-1 ring-stone-200/50" />
                <p
                  className="mt-1 text-[8px] italic text-stone-400"
                  style={{ fontFamily: "'Georgia', serif" }}
                >
                  Figure 1: Architecture diagram
                </p>
                {/* More skeleton text */}
                <div className="mt-2 space-y-1.5">
                  <div className="h-1.5 w-full rounded-full bg-stone-100" />
                  <div className="h-1.5 w-[75%] rounded-full bg-stone-100" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
