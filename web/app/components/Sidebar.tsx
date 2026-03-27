"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { apiJson } from "../lib/api";

interface Subscription {
  id: string;
  channel_name: string;
  youtube_channel_id: string;
}

const NAV_ITEMS = [
  { href: "/", label: "Videos" },
  { href: "/subscriptions", label: "Subscriptions" },
  { href: "/settings", label: "Settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [channels, setChannels] = useState<Subscription[]>([]);

  useEffect(() => {
    apiJson<Subscription[]>("/api/channels")
      .then(setChannels)
      .catch(() => {});
  }, []);

  return (
    <aside className="flex w-56 flex-shrink-0 flex-col border-r border-stone-200 bg-white px-4 py-6">
      <Link href="/" className="text-lg font-semibold tracking-tight">
        Surat
      </Link>

      <nav className="mt-8 space-y-1">
        {NAV_ITEMS.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/" || pathname.startsWith("/videos")
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block rounded-md px-3 py-2 text-sm font-medium ${
                active
                  ? "bg-stone-100 text-stone-900"
                  : "text-stone-600 hover:bg-stone-50 hover:text-stone-900"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      {channels.length > 0 && (
        <div className="mt-8 border-t border-stone-200 pt-4">
          <p className="px-3 text-xs font-medium uppercase tracking-wider text-stone-400">
            Channels
          </p>
          <div className="mt-2 space-y-1">
            {channels.map((ch) => (
              <Link
                key={ch.id}
                href="/subscriptions"
                className="block truncate rounded-md px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-50"
              >
                {ch.channel_name}
              </Link>
            ))}
          </div>
          <Link
            href="/subscriptions"
            className="mt-2 block px-3 text-sm italic text-stone-400 hover:text-stone-600"
          >
            + Add channel
          </Link>
        </div>
      )}

      {channels.length === 0 && (
        <div className="mt-8 border-t border-stone-200 pt-4">
          <Link
            href="/subscriptions"
            className="block px-3 text-sm italic text-stone-400 hover:text-stone-600"
          >
            + Add channel
          </Link>
        </div>
      )}
    </aside>
  );
}
