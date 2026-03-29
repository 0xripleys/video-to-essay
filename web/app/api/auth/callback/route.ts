import { NextRequest, NextResponse } from "next/server";
import { getWorkos, cookiePassword } from "@/app/lib/auth";
import { upsertUser } from "@/app/lib/db";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  if (!code) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  const workos = getWorkos();

  try {
    const authResponse = await workos.userManagement.authenticateWithCode({
      code,
      clientId: process.env.WORKOS_CLIENT_ID!,
      session: { sealSession: true, cookiePassword: cookiePassword() },
    });

    await upsertUser(authResponse.user.email!, authResponse.user.id);

    const isHttps = (process.env.WORKOS_REDIRECT_URI || "").startsWith("https");
    const response = NextResponse.redirect(new URL("/", request.url));
    response.cookies.set("wos_session", authResponse.sealedSession!, {
      httpOnly: true,
      secure: isHttps,
      sameSite: "lax",
      path: "/",
    });
    return response;
  } catch (e) {
    console.error("Auth callback error:", e);
    return NextResponse.redirect(new URL("/", request.url));
  }
}
