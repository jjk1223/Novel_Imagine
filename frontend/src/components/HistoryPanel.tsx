"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchNovels,
  fetchNovel,
  deleteNovel,
  getDownloadUrl,
  type NovelListItem,
  type NovelDetail,
} from "@/lib/api";

interface Props {
  onClose: () => void;
  onResume: (novelId: number) => void;
}

export default function HistoryPanel({ onClose, onResume }: Props) {
  const [novels, setNovels] = useState<NovelListItem[]>([]);
  const [selected, setSelected] = useState<NovelDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setNovels(await fetchNovels());
    } catch {
      /* ignore */
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleSelect(id: number) {
    try {
      setSelected(await fetchNovel(id));
    } catch {
      /* ignore */
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("确认删除该小说？")) return;
    try {
      await deleteNovel(id);
      setSelected(null);
      load();
    } catch {
      /* ignore */
    }
  }

  function handleResume(id: number) {
    onResume(id);
    onClose();
  }

  const canResume = (status: string) =>
    status === "generating" || status === "outline_ready";

  const statusLabel: Record<string, string> = {
    outline_ready: "大纲就绪",
    generating: "中断",
    completed: "已完成",
    pending: "待处理",
  };

  const statusColor: Record<string, string> = {
    outline_ready: "bg-amber-100 text-amber-700",
    generating: "bg-orange-100 text-orange-700",
    completed: "bg-emerald-100 text-emerald-700",
    pending: "bg-slate-100 text-slate-500",
  };

  return (
    <div className="fixed inset-0 z-50 flex bg-black/30 backdrop-blur-sm">
      <div className="m-auto flex h-[85vh] w-[90vw] max-w-5xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
        {/* Left: novel list */}
        <div className="flex w-72 shrink-0 flex-col border-r border-slate-100">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <h2 className="text-sm font-semibold text-slate-800">历史小说</h2>
            <button onClick={onClose} className="text-xs text-slate-400 hover:text-slate-600">
              关闭
            </button>
          </div>

          <div className="flex-1 overflow-y-auto scrollbar-thin">
            {loading ? (
              <p className="p-5 text-xs text-slate-400">加载中…</p>
            ) : novels.length === 0 ? (
              <p className="p-5 text-xs text-slate-400">暂无小说记录</p>
            ) : (
              <ul>
                {novels.map((n) => (
                  <li
                    key={n.id}
                    onClick={() => handleSelect(n.id)}
                    className={`cursor-pointer border-b border-slate-50 px-5 py-3 transition hover:bg-slate-50 ${
                      selected?.id === n.id ? "bg-indigo-50" : ""
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <p className="text-sm font-medium text-slate-800 line-clamp-1">
                        {n.title || "未命名"}
                      </p>
                      <span className={`ml-2 shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                        statusColor[n.status] ?? "bg-slate-100 text-slate-500"
                      }`}>
                        {statusLabel[n.status] ?? n.status}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-slate-400 line-clamp-2">
                      {n.premise}
                    </p>
                    <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-300">
                      <span>{n.chapter_count} 章</span>
                      <span>{new Date(n.created_at).toLocaleDateString("zh-CN")}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Right: novel detail / reader */}
        <div className="flex flex-1 flex-col">
          {selected ? (
            <>
              <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
                <div>
                  <h2 className="text-base font-semibold text-slate-800">
                    《{selected.title}》
                  </h2>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {selected.chapters.filter((c) => c.content).length} / {selected.chapters.length} 章已完成 ·{" "}
                    {new Date(selected.created_at).toLocaleString("zh-CN")}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  {canResume(selected.status) && (
                    <button
                      onClick={() => handleResume(selected.id)}
                      className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-indigo-700"
                    >
                      继续生成
                    </button>
                  )}
                  {selected.status === "completed" && (
                    <>
                      <a
                        href={getDownloadUrl(selected.id, "md")}
                        className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
                      >
                        下载 .md
                      </a>
                      <a
                        href={getDownloadUrl(selected.id, "txt")}
                        className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
                      >
                        下载 .txt
                      </a>
                    </>
                  )}
                  <button
                    onClick={() => handleDelete(selected.id)}
                    className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-500 transition hover:bg-red-50"
                  >
                    删除
                  </button>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto scrollbar-thin">
                <article className="mx-auto max-w-2xl px-8 py-8">
                  {selected.outline && (
                    <blockquote className="mb-8 rounded-lg border-l-4 border-indigo-200 bg-indigo-50/50 py-3 pl-4 pr-3 text-xs leading-relaxed text-slate-600 italic">
                      {(() => {
                        try {
                          const o = JSON.parse(selected.outline);
                          return o.outline || selected.outline;
                        } catch {
                          return selected.outline;
                        }
                      })()}
                    </blockquote>
                  )}

                  {selected.chapters.length === 0 && (
                    <p className="text-sm text-slate-400">该小说尚无章节内容。</p>
                  )}

                  {selected.chapters.map((ch) => (
                    <section key={ch.id} className="mb-10">
                      <h3 className="mb-4 text-center text-base font-semibold text-slate-800">
                        第{ch.chapter_number}章 {ch.title}
                      </h3>
                      {ch.content ? (
                        <div className="whitespace-pre-wrap text-[15px] leading-[1.9] text-slate-700">
                          {ch.content}
                        </div>
                      ) : (
                        <p className="text-center text-sm text-slate-400">（未完成）</p>
                      )}
                    </section>
                  ))}
                </article>
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <p className="text-sm text-slate-400">选择左侧的小说查看详情</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
