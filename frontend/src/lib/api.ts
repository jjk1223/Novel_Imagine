const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export type LLMProvider = "ollama" | "qwen";

export interface HealthStatus {
  status: string;
  sqlite: string;
  neo4j: string;
  llm: string;
}

export interface NovelRequest {
  premise: string;
  genre: string;
  num_chapters: number;
  provider: LLMProvider;
}

export interface CharacterProfile {
  name: string;
  role: string;
  description: string;
}

export interface ChapterOutline {
  chapter_number: number;
  title: string;
  brief: string;
}

export interface OutlineData {
  title: string;
  world_building?: string;
  main_characters?: CharacterProfile[];
  character_relationships?: string;
  writing_style?: string;
  outline: string;
  chapters: ChapterOutline[];
  novel_id?: number;
}

export interface GenerateFromOutlineRequest {
  novel_id: number;
  outline: OutlineData;
  provider: LLMProvider;
}

export interface ResumeRequest {
  novel_id: number;
  provider: LLMProvider;
}

export interface GraphNode {
  id: string;
  label: string;
  properties: Record<string, string>;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  properties: Record<string, string>;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface NovelListItem {
  id: number;
  title: string;
  premise: string;
  status: string;
  created_at: string;
  chapter_count: number;
}

export interface ChapterDetail {
  id: number;
  chapter_number: number;
  title: string;
  summary: string;
  content: string;
  status: string;
}

export interface NovelDetail {
  id: number;
  title: string;
  premise: string;
  outline: string;
  status: string;
  created_at: string;
  chapters: ChapterDetail[];
}

export type SSEEventType = "status" | "text" | "outline" | "graph" | "thinking" | "error" | "done";

export interface SSECallbacks {
  onStatus?: (msg: string) => void;
  onText?: (chunk: string) => void;
  onOutline?: (data: OutlineData) => void;
  onGraph?: (data: GraphData) => void;
  onThinking?: (msg: string) => void;
  onError?: (msg: string) => void;
  onDone?: () => void;
}

// ── Health ──────────────────────────────────────────────

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/api/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

// ── Novels CRUD ─────────────────────────────────────────

export async function fetchNovels(): Promise<NovelListItem[]> {
  const res = await fetch(`${API_BASE}/api/novels`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch novels: ${res.status}`);
  return res.json();
}

export async function fetchNovel(id: number): Promise<NovelDetail> {
  const res = await fetch(`${API_BASE}/api/novels/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch novel: ${res.status}`);
  return res.json();
}

export async function deleteNovel(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/novels/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete novel: ${res.status}`);
}

export function getDownloadUrl(novelId: number, format: "md" | "txt"): string {
  return `${API_BASE}/api/novels/${novelId}/download?format=${format}`;
}

// ── SSE streaming helpers ───────────────────────────────

function streamSSE(
  url: string,
  body: unknown,
  callbacks: SSECallbacks,
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!res.ok) {
        callbacks.onError?.(`Server error: ${res.status}`);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        callbacks.onError?.("No response stream");
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let currentEvent: SSEEventType | null = null;

        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim() as SSEEventType;
          } else if (line.startsWith("data:") && currentEvent) {
            const raw = line.slice(5).trim();
            dispatch(currentEvent, raw, callbacks);
            currentEvent = null;
          } else if (line === "") {
            currentEvent = null;
          }
        }
      }

      callbacks.onDone?.();
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      callbacks.onError?.(String(err));
    }
  })();

  return controller;
}

function dispatch(event: SSEEventType, raw: string, cb: SSECallbacks) {
  switch (event) {
    case "status":
      cb.onStatus?.(raw);
      break;
    case "text":
      cb.onText?.(raw);
      break;
    case "outline":
      try { cb.onOutline?.(JSON.parse(raw)); } catch { /* skip */ }
      break;
    case "graph":
      try { cb.onGraph?.(JSON.parse(raw)); } catch { /* skip */ }
      break;
    case "thinking":
      cb.onThinking?.(raw);
      break;
    case "error":
      cb.onError?.(raw);
      break;
    case "done":
      cb.onDone?.();
      break;
  }
}

// ── Plan (outline only) ─────────────────────────────────

export function startPlan(
  req: NovelRequest,
  callbacks: SSECallbacks,
): AbortController {
  return streamSSE(`${API_BASE}/api/plan`, req, callbacks);
}

// ── Generate (from confirmed outline) ───────────────────

export function startGeneration(
  req: GenerateFromOutlineRequest,
  callbacks: SSECallbacks,
): AbortController {
  return streamSSE(`${API_BASE}/api/generate`, req, callbacks);
}

// ── Resume (continue from breakpoint) ───────────────────

export function startResume(
  req: ResumeRequest,
  callbacks: SSECallbacks,
): AbortController {
  return streamSSE(`${API_BASE}/api/resume`, req, callbacks);
}
