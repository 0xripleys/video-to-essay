import { requireAdminPage } from "@/app/lib/admin";

export default async function ExperimentsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAdminPage();
  return <>{children}</>;
}
