import { notFound } from "next/navigation";
import { getCurrentUser } from "@/app/lib/auth";

const ADMIN_EMAIL = "neerajen.sritharan@gmail.com";

export default async function RunsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const isDev = process.env.NODE_ENV !== "production";
  if (!isDev) {
    const user = await getCurrentUser();
    if (user?.email !== ADMIN_EMAIL) {
      notFound();
    }
  }
  return <>{children}</>;
}
