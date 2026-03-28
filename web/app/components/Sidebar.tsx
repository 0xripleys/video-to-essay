"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Videos" },
  { href: "/subscriptions", label: "Subscriptions" },
  { href: "/settings", label: "Settings" },
];

export default function Sidebar() {
  const pathname = usePathname();

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

      <div className="mt-auto border-t border-stone-200 pt-4">
        <a
          href="/api/auth/logout"
          className="block rounded-md px-3 py-2 text-sm text-stone-500 hover:bg-stone-50 hover:text-stone-900"
        >
          Sign out
        </a>
      </div>
    </aside>
  );
}
