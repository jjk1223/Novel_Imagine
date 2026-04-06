"use client";

import { useEffect, useRef } from "react";
import type { NovelState } from "@/lib/useNovelGeneration";
import type { OutlineData } from "@/lib/api";
import { getDownloadUrl } from "@/lib/api";
import ThinkingPanel from "./ThinkingPanel";
import OutlineEditor from "./OutlineEditor";

interface Props {
  state: NovelState;
  onUpdateOutline: (outline: OutlineData) => void;
  onConfirmGenerate: () => void;
  onReset: () => void;
  onResume: (novelId: number) => void;
}

export default function NovelPanel({ state, onUpdateOutline, onConfirmGenerate, onReset, onResume }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.currentChapterText, state.chapters.length]);

  if (state.phase === "outline_ready" && state.outline) {
    return (
      <main className="flex flex-1 flex-col bg-slate-50">
        <OutlineEditor
          outline={state.outline}
          onUpdate={onUpdateOutline}
          onConfirm={onConfirmGenerate}
          onReset={onReset}
        />
      </main>
    );
  }

  const hasContent =
    state.chapters.length > 0 || state.currentChapterText.length > 0;

  const showResumeBanner = state.phase === "error" && state.novelId;

  return (
    <main className="flex flex-1 flex-col bg-slate-50">
      <div className="flex shrink-0 items-center justify-between border-b border-slate-100 bg-white px-6 py-3">
        <h2 className="text-sm font-semibold text-slate-700">
          {state.outline?.title ? `《${state.outline.title}》` : "小说内容"}
        </h2>
        <div className="flex items-center gap-3">
          {state.outline && (
            <span className="text-xs text-slate-400">
              {state.chapters.length} / {state.outline.chapters.length} 章
            </span>
          )}
          {state.phase === "done" && state.novelId && (
            <div className="flex gap-1.5">
              <a
                href={getDownloadUrl(state.novelId, "md")}
                className="rounded border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-500 transition hover:bg-slate-50"
              >
                .md
              </a>
              <a
                href={getDownloadUrl(state.novelId, "txt")}
                className="rounded border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-500 transition hover:bg-slate-50"
              >
                .txt
              </a>
            </div>
          )}
        </div>
      </div>

      {/* Resume banner on error */}
      {showResumeBanner && (
        <div className="flex items-center justify-between border-b border-orange-200 bg-orange-50 px-6 py-3">
          <div className="flex items-center gap-2">
            <svg className="h-4 w-4 text-orange-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            <span className="text-xs font-medium text-orange-700">
              生成中断 — 已完成的章节已保存
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onResume(state.novelId!)}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-indigo-700"
            >
              断点续写
            </button>
            <button
              onClick={onReset}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-500 transition hover:bg-white"
            >
              放弃
            </button>
          </div>
        </div>
      )}

      <ThinkingPanel entries={state.thinkingLog} />

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {hasContent ? (
          <article className="mx-auto max-w-2xl px-8 py-8">
            {state.chapters.map((ch) => (
              <section key={ch.number} className="mb-10">
                <h3 className="mb-4 text-center text-base font-semibold text-slate-800">
                  第{ch.number}章 {ch.title}
                </h3>
                <div className="whitespace-pre-wrap text-[15px] leading-[1.9] text-slate-700">
                  {ch.text}
                </div>
              </section>
            ))}

            {state.currentChapterText && (
              <section className="mb-10">
                {state.outline?.chapters[state.chapters.length] && (
                  <h3 className="mb-4 text-center text-base font-semibold text-slate-800">
                    第{state.outline.chapters[state.chapters.length].chapter_number}章{" "}
                    {state.outline.chapters[state.chapters.length].title}
                  </h3>
                )}
                <div className="whitespace-pre-wrap text-[15px] leading-[1.9] text-slate-700">
                  {state.currentChapterText}
                  <span className="inline-block h-4 w-0.5 animate-pulse bg-indigo-500" />
                </div>
              </section>
            )}

            <div ref={bottomRef} />
          </article>
        ) : (
          <div className="flex h-full items-center justify-center p-8">
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-50">
                <svg className="h-8 w-8 text-indigo-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                </svg>
              </div>
              <p className="text-sm font-medium text-slate-500">输入故事构思并生成大纲</p>
              <p className="mt-1 text-xs text-slate-400">
                AI 将生成完整企划书（世界观、角色、关系、章节大纲）
              </p>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
