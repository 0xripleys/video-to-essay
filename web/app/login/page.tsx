"use client";

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-sm space-y-6 text-center">
        <h1 className="text-2xl font-bold tracking-tight">Surat</h1>
        <p className="text-stone-500">
          Turn YouTube videos into illustrated essays.
        </p>
        <a
          href="/api/auth/login"
          className="inline-block w-full rounded-lg bg-stone-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-stone-800"
        >
          Sign in with email
        </a>
      </div>
    </div>
  );
}
