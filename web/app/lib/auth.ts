import { WorkOS } from "@workos-inc/node";
import { cookies } from "next/headers";
import { getUserByWorkosId, upsertUser, type User } from "./db";

let _workos: WorkOS | null = null;

export function getWorkos(): WorkOS {
  if (!_workos) {
    _workos = new WorkOS(process.env.WORKOS_API_KEY!, {
      clientId: process.env.WORKOS_CLIENT_ID!,
    });
  }
  return _workos;
}

export function cookiePassword(): string {
  const pw = process.env.WORKOS_COOKIE_PASSWORD;
  if (!pw) throw new Error("WORKOS_COOKIE_PASSWORD must be set");
  return pw;
}

export async function getCurrentUser(): Promise<User | null> {
  // Dev mode: bypass auth when WorkOS is not configured
  if (!process.env.WORKOS_API_KEY) {
    let devUser = await getUserByWorkosId("dev_user");
    if (!devUser) {
      devUser = await upsertUser("dev@localhost", "dev_user");
    }
    return devUser;
  }

  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("wos_session")?.value;
  if (!sessionCookie) return null;

  const workos = getWorkos();
  const pw = cookiePassword();

  try {
    // Try to get session data (includes full user object from sealed cookie)
    const sessionData = await workos.userManagement.getSessionFromCookie({
      sessionData: sessionCookie,
      cookiePassword: pw,
    });

    if (sessionData?.user) {
      return getUserByWorkosId(sessionData.user.id);
    }

    // Session expired — try refresh via loadSealedSession
    const session = workos.userManagement.loadSealedSession({
      sessionData: sessionCookie,
      cookiePassword: pw,
    });

    const refreshResult = await session.refresh();
    if (!refreshResult.authenticated || !refreshResult.sealedSession) {
      return null;
    }

    // Get user from refreshed session
    const refreshedData = await workos.userManagement.getSessionFromCookie({
      sessionData: refreshResult.sealedSession,
      cookiePassword: pw,
    });

    if (refreshedData?.user) {
      return getUserByWorkosId(refreshedData.user.id);
    }

    return null;
  } catch {
    return null;
  }
}

export async function requireAuth(): Promise<User> {
  const user = await getCurrentUser();
  if (!user) {
    throw new Error("Not authenticated");
  }
  return user;
}
