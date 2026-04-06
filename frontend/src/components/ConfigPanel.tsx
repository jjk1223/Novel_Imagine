"use client";

import { useState } from "react";
import type { NovelRequest, LLMProvider } from "@/lib/api";
import type { GenerationPhase, NovelState } from "@/lib/useNovelGeneration";

const GENRES = ["奇幻", "科幻", "悬疑", "言情", "武侠", "历史", "都市", "军事"];

interface Props {
  state: NovelState;
  onPlan: (req: NovelRequest) => void;
  onSetProvider: (provider: LLMProvider) => void;
  onStop: () => void;
  onReset: () => void;
  onShowHistory: () => void;
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

const busyPhases: GenerationPhase[] = ["planning", "writing", "extracting"];

export default function ConfigPanel({ state, onPlan, onSetProvider, onStop, onReset, onShowHistory }: Props) {
  const [premise, setPremise] = useState("");
  const [genre, setGenre] = useState("奇幻");
  const [numChapters, setNumChapters] = useState(3);

  const busy = busyPhases.includes(state.phase);
  const showForm = state.phase === "idle" || state.phase === "error";

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!premise.trim() || busy) return;
    onPlan({ premise: premise.trim(), genre, num_chapters: numChapters, provider: state.provider });
  }

  const activeChapter = state.phase === "writing" ? state.chapters.length + 1 : null;

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-slate-200 bg-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
        <h2 className="text-sm font-semibold text-slate-700">配置</h2>
        <button
          onClick={onShowHistory}
          className="text-xs text-indigo-500 transition hover:text-indigo-700"
        >
          历史记录
        </button>
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex flex-1 flex-col gap-3.5 overflow-y-auto p-5 scrollbar-thin"
      >
        {/* Model selector — always visible when not writing */}
        {!busy && state.phase !== "done" && (
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">模型</label>
            <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
              <button
                type="button"
                onClick={() => onSetProvider("ollama")}
                className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  state.provider === "ollama"
                    ? "bg-white text-indigo-600 shadow-sm"
                    : "text-slate-400 hover:text-slate-600"
                }`}
              >
                本地 Ollama
              </button>
              <button
                type="button"
                onClick={() => onSetProvider("qwen")}
                className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  state.provider === "qwen"
                    ? "bg-white text-indigo-600 shadow-sm"
                    : "text-slate-400 hover:text-slate-600"
                }`}
              >
                在线 Qwen
              </button>
            </div>
          </div>
        )}

        {/* Provider badge during busy */}
        {busy && (
          <div className="flex items-center gap-1.5 rounded-lg bg-slate-50 px-3 py-1.5">
            <span className={`h-1.5 w-1.5 rounded-full ${state.provider === "ollama" ? "bg-emerald-400" : "bg-blue-400"}`} />
            <span className="text-[11px] text-slate-500">
              {state.provider === "ollama" ? "本地 Ollama" : "在线 Qwen API"}
            </span>
          </div>
        )}

        {showForm && (
          <>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-500">故事构思</label>
              <textarea
                rows={6}
                value={premise}
                onChange={(e) => setPremise(e.target.value)}
                placeholder={"描述你的故事构想…\n\n越详细越好：主角背景、核心冲突、你期望的风格、世界观、关键剧情点等"}
                className="w-full resize-none rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-500">题材</label>
              <select
                value={genre}
                onChange={(e) => setGenre(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              >
                {GENRES.map((g) => <option key={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-500">章节数</label>
              <input
                type="number"
                value={numChapters}
                onChange={(e) => setNumChapters(Number(e.target.value))}
                min={1} max={50}
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              />
            </div>
            <button
              type="submit"
              disabled={!premise.trim()}
              className="mt-1 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 active:bg-indigo-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              生成大纲
            </button>
          </>
        )}

        {state.phase === "planning" && (
          <div className="text-center text-xs text-slate-500">
            <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center">
              <Spinner />
            </div>
            <p className="font-medium">AI 正在创作企划书…</p>
            <p className="mt-1 text-slate-400">包含世界观、角色档案、关系网络等</p>
          </div>
        )}

        {state.phase === "outline_ready" && (
          <div className="text-center text-xs text-slate-500">
            <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-emerald-50 text-emerald-500">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            </div>
            <p className="font-medium text-emerald-600">企划书已就绪</p>
            <p className="mt-1 text-slate-400">在右侧编辑区预览和修改</p>
          </div>
        )}

        {busy && (
          <button
            type="button"
            onClick={onStop}
            className="mt-1 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 transition hover:bg-red-100"
          >
            停止生成
          </button>
        )}

        {state.phase === "done" && (
          <button type="button" onClick={onReset}
            className="mt-1 rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50">
            重新开始
          </button>
        )}

        {state.phase === "error" && state.error && (
          <div className="mt-1 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
            {state.error}
          </div>
        )}

        {state.statusMessage && (
          <div className="mt-1 flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2">
            {busy && <Spinner />}
            <span className="text-xs text-slate-500">{state.statusMessage}</span>
          </div>
        )}
      </form>

      {/* Chapter progress */}
      {state.outline && (state.phase === "writing" || state.phase === "extracting" || state.phase === "done") && (
        <div className="flex max-h-[45%] flex-col border-t border-slate-100">
          <div className="px-5 py-2">
            <h2 className="text-xs font-semibold text-slate-600">
              章节进度 ({state.chapters.length}/{state.outline.chapters.length})
            </h2>
          </div>
          <div className="flex-1 overflow-y-auto px-5 pb-4 scrollbar-thin">
            <ol className="space-y-1">
              {state.outline.chapters.map((ch) => {
                const isDone = state.chapters.some((c) => c.number === ch.chapter_number);
                const isActive = activeChapter === ch.chapter_number;
                return (
                  <li
                    key={ch.chapter_number}
                    className={`rounded-md px-2.5 py-1.5 text-xs transition ${
                      isActive
                        ? "bg-indigo-50 font-medium text-indigo-700"
                        : isDone
                          ? "text-slate-500"
                          : "text-slate-400"
                    }`}
                  >
                    <span className="font-mono text-[10px] text-slate-400">
                      {String(ch.chapter_number).padStart(2, "0")}
                    </span>{" "}
                    {ch.title}
                    {isDone && <span className="ml-1.5 text-emerald-500">&#10003;</span>}
                    {isActive && busy && (
                      <span className="ml-1.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" />
                    )}
                  </li>
                );
              })}
            </ol>
          </div>
        </div>
      )}
    </aside>
  );
}
