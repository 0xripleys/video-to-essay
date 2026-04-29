import { notFound } from "next/navigation";
import { NextResponse } from "next/server";
import { getCurrentUser } from "@/app/lib/auth";

export const ADMIN_EMAIL = "neerajen.sritharan@gmail.com";

/** Page-level guard: redirect non-admins to 404 in production. */
export async function requireAdminPage(): Promise<void> {
  if (process.env.NODE_ENV !== "production") return;
  const user = await getCurrentUser();
  if (user?.email !== ADMIN_EMAIL) {
    notFound();
  }
}

/** Route-handler guard: returns a 404 NextResponse for non-admins, null otherwise. */
export async function requireAdminRoute(): Promise<NextResponse | null> {
  if (process.env.NODE_ENV !== "production") return null;
  const user = await getCurrentUser();
  if (user?.email !== ADMIN_EMAIL) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  return null;
}
