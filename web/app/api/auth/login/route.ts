import { redirect } from "next/navigation";
import { getWorkos } from "@/app/lib/auth";

export async function GET() {
  const workos = getWorkos();
  const redirectUri =
    process.env.WORKOS_REDIRECT_URI || "http://localhost:3000/api/auth/callback";

  const url = workos.userManagement.getAuthorizationUrl({
    provider: "authkit",
    redirectUri,
    clientId: process.env.WORKOS_CLIENT_ID!,
  });

  redirect(url);
}
