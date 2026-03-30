export default function Landing() {
  return (
    <div className="flex min-h-screen flex-col bg-stone-50">
      {/* Nav */}
      <nav className="flex items-center justify-between px-8 py-5">
        <a href="/" className="text-[15px] font-semibold tracking-tight text-stone-900">
          Scrivi
        </a>
        <a
          href="/api/auth/login"
          className="text-sm text-stone-500 transition-colors hover:text-stone-900"
        >
          Sign in
        </a>
      </nav>

      {/* Hero */}
      <div className="flex flex-col items-center px-8 pt-24">
        <div className="w-full max-w-lg text-center">
          <h1 className="text-3xl font-bold leading-tight tracking-tight text-stone-900">
            Turn YouTube videos into polished transcripts — delivered to your inbox
          </h1>
          <p className="mx-auto mt-4 max-w-md text-[15px] leading-relaxed text-stone-500">
            Paste a link for a one-off, or subscribe to a channel to get every new video
            automatically.
          </p>
          <a
            href="/api/auth/login"
            className="mt-6 inline-block rounded-lg bg-stone-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-stone-800"
          >
            Get started
          </a>
        </div>
      </div>

      {/* Example essay card */}
      <div className="mx-auto mt-16 w-full max-w-[650px] px-8 pb-16">
        <div className="relative overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm">
          {/* Video source */}
          <img
            src="/example/thumbnail.jpg"
            alt="Markets Weekly March 28, 2026"
            className="aspect-video w-full object-cover"
          />
          <div className="border-b border-stone-100 px-6 py-3 sm:px-8">
            <p className="text-sm font-semibold text-stone-800">
              Markets Weekly March 28, 2026
            </p>
            <p className="mt-0.5 text-xs text-stone-400">Joseph Wang</p>
          </div>

          {/* Essay content */}
          <div className="p-6 sm:p-8">
            <article>
              <h1
                className="text-2xl font-bold leading-tight tracking-tight text-stone-900"
                style={{ fontFamily: "'Georgia', serif" }}
              >
                Markets Weekly: The Middle East War and What It Means for Everything
              </h1>

              <p className="mt-4 text-[15px] leading-relaxed text-stone-700">
                Hello, my friends. So today is March 28 and this is Markets Weekly.
              </p>

              <p className="mt-3 text-[15px] leading-relaxed text-stone-700">
                For weeks, we&apos;ve been talking about how the S&amp;P 500 has been losing
                momentum. Last week, it looks like it&apos;s outright breaking down. Coincidentally,
                next week is the one year anniversary of Liberation Day. And as what we all recall,
                that was a very very exciting time in the markets.
              </p>

              <p className="mt-3 text-[15px] leading-relaxed text-stone-700">
                So today, there&apos;s really only one thing to talk about, one thing that
                matters&mdash;the war in the Middle East.
              </p>

              <h2
                className="mt-8 text-lg font-bold text-stone-900"
                style={{ fontFamily: "'Georgia', serif" }}
              >
                The Economic and Financial Fallout
              </h2>

              <p className="mt-3 text-[15px] leading-relaxed text-stone-700">
                <strong>
                  The global economy has been nuked and we are moving into the phase where, due to
                  radiation sickness, we are not feeling well.
                </strong>
              </p>

              <p className="mt-3 text-[15px] leading-relaxed text-stone-700">
                The Strait of Hormuz remains closed. There&apos;s only a few ships passing through
                each day. Those ships seem to largely be Iranian vessels sending crude oil to China.
                Iran is actually selling more oil today than it did before the war. So that means
                that on net, the global economy has a tremendous tremendous negative supply shock in
                oil.
              </p>

              <figure className="mt-5">
                <img
                  src="/example/frame_0020.jpg"
                  alt="Bar chart showing vessel traffic through the Strait of Hormuz"
                  className="w-full rounded-lg"
                />
                <figcaption className="mt-1.5 text-center text-xs italic text-stone-400">
                  Figure 1: Vessel traffic through the Strait of Hormuz since February 2026
                </figcaption>
              </figure>

              <p className="mt-4 text-[15px] leading-relaxed text-stone-700">
                That supply shock has in part been mitigated by factors such as Saudi Arabia sending
                oil through a pipe to the Red Sea and also the release of emergency oil stockpiles
                throughout the world. But at the end of the day, the world still is receiving on a
                flow basis fewer barrels than before, and that&apos;s showing up in pricing.
              </p>

              <figure className="mt-5">
                <img
                  src="/example/frame_0030.jpg"
                  alt="Line chart showing jet fuel prices surging above other petroleum products"
                  className="w-full rounded-lg"
                />
                <figcaption className="mt-1.5 text-center text-xs italic text-stone-400">
                  Figure 2: Jet fuel prices surging ahead of other petroleum products
                </figcaption>
              </figure>
            </article>
          </div>

          {/* Gradient fade */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-48 bg-gradient-to-t from-white to-transparent" />
        </div>
      </div>
    </div>
  );
}
