/**
 * Server-side helpers for reading the experiments/ tree on S3.
 *
 * Layout:
 *   experiments/<exp_id>/manifest.json
 *   experiments/<exp_id>/<video_id>/<step>/<slug>/{output/, score.json, meta.json, llm_calls/}
 *
 * The viewer reads from S3 in production. Locally during dev, we fall back to
 * the same layout under <repo>/experiments/.
 */

import { GetObjectCommand, ListObjectsV2Command, S3Client } from "@aws-sdk/client-s3";
import fs from "node:fs";
import path from "node:path";

const bucket = process.env.S3_BUCKET_NAME;
const region = process.env.AWS_REGION || "us-east-1";

let client: S3Client | null = null;

function getClient(): S3Client {
  if (!client) {
    client = new S3Client({ region });
  }
  return client;
}

const LOCAL_BASE = path.resolve(process.cwd(), "..", "experiments");
const LOCAL_BASE_FALLBACK = path.resolve(process.cwd(), "experiments");

function getLocalBase(): string | null {
  for (const p of [LOCAL_BASE, LOCAL_BASE_FALLBACK]) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

export interface CellSummary {
  video_id: string;
  variant: string;
  slug: string;
  status: string;
  cost_usd: number | null;
  wall_ms: number;
  score_overall: number | null;
}

export interface Manifest {
  exp_id: string;
  step: string;
  videos: string[];
  variants: string[];
  started_at: string;
  finished_at: string;
  judge_model: string;
  cells: CellSummary[];
  ok_count: number;
  fail_count: number;
  configs?: Record<string, Record<string, string>>;
  spec_hash?: string;
}

async function s3GetText(key: string): Promise<string | null> {
  if (!bucket) return null;
  try {
    const resp = await getClient().send(
      new GetObjectCommand({ Bucket: bucket, Key: key }),
    );
    return (await resp.Body?.transformToString("utf-8")) ?? null;
  } catch {
    return null;
  }
}

async function s3ListPrefixes(prefix: string): Promise<string[]> {
  if (!bucket) return [];
  const out: string[] = [];
  let token: string | undefined;
  do {
    const resp = await getClient().send(
      new ListObjectsV2Command({
        Bucket: bucket,
        Prefix: prefix,
        Delimiter: "/",
        ContinuationToken: token,
      }),
    );
    for (const cp of resp.CommonPrefixes ?? []) {
      if (cp.Prefix) out.push(cp.Prefix);
    }
    token = resp.NextContinuationToken;
  } while (token);
  return out;
}

async function s3ListKeys(prefix: string): Promise<string[]> {
  if (!bucket) return [];
  const out: string[] = [];
  let token: string | undefined;
  do {
    const resp = await getClient().send(
      new ListObjectsV2Command({
        Bucket: bucket,
        Prefix: prefix,
        ContinuationToken: token,
      }),
    );
    for (const obj of resp.Contents ?? []) {
      if (obj.Key) out.push(obj.Key);
    }
    token = resp.NextContinuationToken;
  } while (token);
  return out;
}

function localReadText(rel: string): string | null {
  const base = getLocalBase();
  if (!base) return null;
  const full = path.join(base, rel);
  if (!fs.existsSync(full)) return null;
  try {
    return fs.readFileSync(full, "utf-8");
  } catch {
    return null;
  }
}

function localListDirs(rel: string): string[] {
  const base = getLocalBase();
  if (!base) return [];
  const full = path.join(base, rel);
  if (!fs.existsSync(full)) return [];
  return fs
    .readdirSync(full, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name);
}

/** List exp_ids, newest first. */
export async function listExpIds(): Promise<string[]> {
  // Try S3 first
  const s3Prefixes = await s3ListPrefixes("experiments/");
  const fromS3 = s3Prefixes.map((p) => p.slice("experiments/".length).replace(/\/$/, ""));

  // Merge in local-only experiments (dev mode)
  const local = localListDirs("");

  const all = Array.from(new Set([...fromS3, ...local])).filter(Boolean);
  // exp_id starts with YYYYMMDD-HHMMSS so reverse lexical sort = newest first
  all.sort().reverse();
  return all;
}

export async function getManifest(expId: string): Promise<Manifest | null> {
  const text =
    (await s3GetText(`experiments/${expId}/manifest.json`)) ??
    localReadText(`${expId}/manifest.json`);
  if (!text) return null;
  try {
    return JSON.parse(text) as Manifest;
  } catch {
    return null;
  }
}

export async function listManifests(expIds: string[]): Promise<Manifest[]> {
  const results = await Promise.all(expIds.map((id) => getManifest(id)));
  return results.filter((m): m is Manifest => m !== null);
}

/** Fetch a variant's meta.json. */
export async function getCellMeta(
  expId: string,
  videoId: string,
  step: string,
  slug: string,
): Promise<Record<string, unknown> | null> {
  const rel = `${videoId}/${step}/${slug}/meta.json`;
  const text =
    (await s3GetText(`experiments/${expId}/${rel}`)) ??
    localReadText(`${expId}/${rel}`);
  if (!text) return null;
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export async function getCellScore(
  expId: string,
  videoId: string,
  step: string,
  slug: string,
): Promise<Record<string, unknown> | null> {
  const rel = `${videoId}/${step}/${slug}/score.json`;
  const text =
    (await s3GetText(`experiments/${expId}/${rel}`)) ??
    localReadText(`${expId}/${rel}`);
  if (!text) return null;
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** Fetch a variant's primary text output (essay.md, essay_final.md, etc). */
export async function getCellOutput(
  expId: string,
  videoId: string,
  step: string,
  slug: string,
  filename: string,
): Promise<string | null> {
  const rel = `${videoId}/${step}/${slug}/output/${filename}`;
  return (
    (await s3GetText(`experiments/${expId}/${rel}`)) ??
    localReadText(`${expId}/${rel}`)
  );
}

/** Fetch a full-pipeline variant's per-step output. */
export async function getFullPipelineStepOutput(
  expId: string,
  videoId: string,
  configName: string,
  stepDir: string,
  filename: string,
): Promise<string | null> {
  const rel = `${videoId}/all/${configName}/steps/${stepDir}/output/${filename}`;
  return (
    (await s3GetText(`experiments/${expId}/${rel}`)) ??
    localReadText(`${expId}/${rel}`)
  );
}

/** Filename whose presence we look up to render a side-by-side panel.
 *  For single-step `essay`, the output is `essay.md`; for `place_images`,
 *  `essay_final.md`; for `all`, the per-step file depends on `stepDir`.
 */
export function primaryOutputFilename(step: string): string {
  switch (step) {
    case "essay":
    case "summarize":
      return "essay.md";
    case "place_images":
      return "essay_final.md";
    case "sponsor_filter":
      return "transcript_clean.txt";
    default:
      return "output.txt";
  }
}

/** List llm_calls/*.json filenames for a cell (no extensions stripped). */
export async function listLlmCalls(
  expId: string,
  videoId: string,
  step: string,
  slug: string,
): Promise<string[]> {
  const prefix = `experiments/${expId}/${videoId}/${step}/${slug}/llm_calls/`;
  // S3
  const keys = await s3ListKeys(prefix);
  if (keys.length > 0) {
    return keys
      .map((k) => k.slice(prefix.length))
      .filter((n) => n.endsWith(".json"))
      .sort();
  }
  // Local fallback
  const base = getLocalBase();
  if (!base) return [];
  const dir = path.join(base, expId, videoId, step, slug, "llm_calls");
  if (!fs.existsSync(dir)) return [];
  try {
    return fs
      .readdirSync(dir)
      .filter((n) => n.endsWith(".json"))
      .sort();
  } catch {
    return [];
  }
}

/** Fetch one llm_calls/<file> as parsed JSON (or raw text if not parseable). */
export async function getLlmCall(
  expId: string,
  videoId: string,
  step: string,
  slug: string,
  filename: string,
): Promise<Record<string, unknown> | null> {
  const rel = `${videoId}/${step}/${slug}/llm_calls/${filename}`;
  const text =
    (await s3GetText(`experiments/${expId}/${rel}`)) ??
    localReadText(`${expId}/${rel}`);
  if (!text) return null;
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function fullPipelineStepFilename(stepDir: string): string {
  switch (stepDir) {
    case "02_filter_sponsors":
      return "transcript_clean.txt";
    case "03_essay":
      return "essay.md";
    case "04_frames":
      return "classifications.json";
    case "05_place_images":
      return "essay_final.md";
    default:
      return "output.txt";
  }
}
