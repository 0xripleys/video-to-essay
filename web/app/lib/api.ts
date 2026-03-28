/** Fetch wrapper that redirects to login on 401. */
export async function api(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(path, {
    ...init,
    credentials: "include",
  });
  if (res.status === 401) {
    window.location.href = "/";
    throw new Error("Not authenticated");
  }
  return res;
}

export async function apiJson<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await api(path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Server error (${res.status})`);
  }
  return res.json();
}
