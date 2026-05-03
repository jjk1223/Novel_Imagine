"use client";

import { useCallback, useRef, useState } from "react";
import {
  startPlan,
  startGeneration,
  startResume,
  type GraphData,
  type NovelRequest,
  type OutlineData,
  type LLMProvider,
  type ReflectEventData,
  type ReverseOutlineEventData,
} from "./api";

export type GenerationPhase =
  | "idle"
  | "planning"
  | "outline_ready"
  | "writing"
  | "extracting"
  | "reflecting"
  | "done"
  | "error";

export interface ChapterContent {
  number: number;
  title: string;
  text: string;
}

export interface ThinkingEntry {
  timestamp: number;
  message: string;
}

export interface ReflectIssue {
  chapter: number;
  issues: string[];
  reasoning: string;
}

export interface NovelState {
  phase: GenerationPhase;
  statusMessage: string;
  novelId: number | null;
  outline: OutlineData | null;
  chapters: ChapterContent[];
  currentChapterText: string;
  graph: GraphData;
  thinkingLog: ThinkingEntry[];
  error: string | null;
  provider: LLMProvider;
  reflectIssues: ReflectIssue[];
}

const INITIAL_STATE: NovelState = {
  phase: "idle",
  statusMessage: "",
  novelId: null,
  outline: null,
  chapters: [],
  currentChapterText: "",
  graph: { nodes: [], edges: [] },
  thinkingLog: [],
  error: null,
  provider: "ollama",
  reflectIssues: [],
};

function makeWriteCallbacks(
  setState: React.Dispatch<React.SetStateAction<NovelState>>,
  chapterIndexRef: React.MutableRefObject<number>,
  abortRef: React.MutableRefObject<AbortController | null>,
) {
  return {
    onStatus(msg: string) {
      setState((p) => {
        let newState = { ...p };

        if (msg.includes("撰写第") && p.currentChapterText.length > 0) {
          newState.chapters = finalizeChapter(p);
          newState.currentChapterText = "";
          chapterIndexRef.current++;
        }

        let phase: GenerationPhase = p.phase;
        if (msg.includes("撰写")) phase = "writing";
        else if (msg.includes("提取")) phase = "extracting";
        else if (msg.includes("审校") || msg.includes("改写")) phase = "reflecting";
        else if (msg.includes("完成")) phase = "done";

        return { ...newState, phase, statusMessage: msg };
      });
    },
    onText(chunk: string) {
      setState((p) => {
        if (p.phase === "planning" || p.phase === "outline_ready") return p;
        return { ...p, currentChapterText: p.currentChapterText + chunk };
      });
    },
    onOutline(data: OutlineData) {
      setState((p) => ({
        ...p,
        outline: data,
        novelId: data.novel_id ?? p.novelId,
        currentChapterText: "",
      }));
    },
    onGraph(data: GraphData) {
      setState((p) => ({ ...p, graph: data }));
    },
    onThinking(msg: string) {
      setState((p) => ({
        ...p,
        thinkingLog: [...p.thinkingLog, { timestamp: Date.now(), message: msg }],
      }));
    },
    onError(msg: string) {
      setState((p) => ({ ...p, phase: "error", error: msg }));
    },
    onDone() {
      setState((p) => {
        const chapters = finalizeChapter(p);
        return {
          ...p,
          phase: "done",
          chapters,
          currentChapterText: "",
          statusMessage: p.statusMessage || "生成完成",
        };
      });
    },
    onReflect(data: ReflectEventData) {
      setState((p) => {
        const currentChapter = p.chapters.length + (p.currentChapterText ? 1 : 0);
        const newIssues = data.issues_found
          ? [...p.reflectIssues, { chapter: currentChapter, issues: data.issues, reasoning: data.reasoning }]
          : p.reflectIssues;
        return { ...p, reflectIssues: newIssues };
      });
    },
    onReverseOutline(_data: ReverseOutlineEventData) {
      // Reverse outline info is already captured in thinkingLog events
    },
  };
}

export function useNovelGeneration() {
  const [state, setState] = useState<NovelState>(INITIAL_STATE);
  const abortRef = useRef<AbortController | null>(null);
  const chapterIndexRef = useRef(0);

  const setProvider = useCallback((provider: LLMProvider) => {
    setState((prev) => ({ ...prev, provider }));
  }, []);

  // ── Phase 1: Generate outline ──────────────────────────
  const plan = useCallback((req: NovelRequest) => {
    if (abortRef.current) abortRef.current.abort();

    setState((prev) => ({
      ...INITIAL_STATE,
      phase: "planning",
      statusMessage: "正在构思大纲…",
      provider: req.provider,
    }));

    const controller = startPlan(req, {
      onStatus(msg) {
        setState((prev) => ({ ...prev, statusMessage: msg }));
      },
      onOutline(data) {
        setState((prev) => ({
          ...prev,
          outline: data,
          novelId: data.novel_id ?? null,
          phase: "outline_ready",
          statusMessage: "大纲已生成，请编辑确认后开始创作",
        }));
      },
      onThinking(msg) {
        setState((prev) => ({
          ...prev,
          thinkingLog: [...prev.thinkingLog, { timestamp: Date.now(), message: msg }],
        }));
      },
      onError(msg) {
        setState((prev) => ({ ...prev, phase: "error", error: msg }));
      },
      onDone() {
        setState((prev) => {
          if (prev.phase === "outline_ready") return prev;
          return { ...prev, phase: prev.outline ? "outline_ready" : "error" };
        });
      },
    });

    abortRef.current = controller;
  }, []);

  const updateOutline = useCallback((outline: OutlineData) => {
    setState((prev) => ({ ...prev, outline }));
  }, []);

  // ── Phase 2: Write from confirmed outline ──────────────
  const confirmAndGenerate = useCallback(() => {
    setState((prev) => {
      if (!prev.outline || !prev.novelId) return prev;

      const controller = startGeneration(
        { novel_id: prev.novelId, outline: prev.outline, provider: prev.provider },
        makeWriteCallbacks(setState, chapterIndexRef, abortRef),
      );

      abortRef.current = controller;

      return {
        ...prev,
        phase: "writing" as GenerationPhase,
        statusMessage: "开始创作…",
        chapters: [],
        currentChapterText: "",
        thinkingLog: [],
        error: null,
        reflectIssues: [],
      };
    });
  }, []);

  // ── Resume from breakpoint ─────────────────────────────
  const resume = useCallback((novelId: number, provider?: LLMProvider) => {
    if (abortRef.current) abortRef.current.abort();

    const p = provider ?? state.provider;

    setState((prev) => ({
      ...prev,
      phase: "writing",
      statusMessage: "正在恢复续写…",
      novelId,
      chapters: [],
      currentChapterText: "",
      thinkingLog: [],
      error: null,
      provider: p,
      reflectIssues: [],
    }));

    const controller = startResume(
      { novel_id: novelId, provider: p },
      makeWriteCallbacks(setState, chapterIndexRef, abortRef),
    );

    abortRef.current = controller;
  }, [state.provider]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => ({ ...prev, phase: "idle", statusMessage: "已停止" }));
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => ({ ...INITIAL_STATE, provider: prev.provider }));
  }, []);

  return { state, setProvider, plan, updateOutline, confirmAndGenerate, resume, stop, reset };
}

function finalizeChapter(prev: NovelState): ChapterContent[] {
  if (prev.currentChapterText.length === 0) return prev.chapters;

  const idx = prev.chapters.length;
  const outlineEntry = prev.outline?.chapters[idx];

  return [
    ...prev.chapters,
    {
      number: outlineEntry?.chapter_number ?? idx + 1,
      title: outlineEntry?.title ?? `第${idx + 1}章`,
      text: prev.currentChapterText,
    },
  ];
}
