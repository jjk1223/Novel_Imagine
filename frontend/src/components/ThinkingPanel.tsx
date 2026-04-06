"use client";

import { useEffect, useRef, useState } from "react";
import type { ThinkingEntry } from "@/lib/useNovelGeneration";

interface Props {
  entries: ThinkingEntry[];
}

function tagColor(msg: string): string {
  if (msg.includes("[GraphRAG]")) return "text-violet-600";
  if (msg.includes("[Extractor]")) return "text-amber-600";
  if (msg.includes("[记忆层]")) return "text-cyan-600";
  if (msg.includes("[摘要]")) return "text-emerald-600";
  if (msg.includes("[完成]")) return "text-indigo-600";
  return "text-slate-500";
}

function extractTag(msg: string): { tag: string; rest: string } {
  const match = msg.match(/^\[([^\]]+)\]\s*/);
  if (match) return { tag: match[1], rest: msg.slice(match[0].length) };
  return { tag: "", rest: msg };
}

export default function ThinkingPanel({ entries }: Props) {
  const [expanded, setExpanded] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (expanded) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [entries.length, expanded]);

  if (entries.length === 0) return null;

  return (
    <div className="border-b border-slate-100 bg-white">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-6 py-2 text-left text-xs font-medium text-slate-500 transition hover:bg-slate-50"
      >
        <svg
          className={`h-3 w-3 shrink-0 transition-transform ${expanded ? "rotate-90" : ""}`}
          viewBox="0 0 12 12"
          fill="currentColor"
        >
          <path d="M4 2l4 4-4 4V2z" />
        </svg>
        思考过程
        <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] tabular-nums text-slate-400">
          {entries.length}
        </span>
      </button>

      {expanded && (
        <div className="max-h-48 overflow-y-auto px-6 pb-3 scrollbar-thin">
          <div className="space-y-1">
            {entries.map((entry, i) => {
              const { tag, rest } = extractTag(entry.message);
              const color = tagColor(entry.message);
              return (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <span className="mt-px shrink-0 font-mono text-[10px] text-slate-300">
                    {new Date(entry.timestamp).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </span>
                  {tag && (
                    <span className={`shrink-0 rounded bg-slate-50 px-1 py-0.5 font-medium ${color}`}>
                      {tag}
                    </span>
                  )}
                  <span className="text-slate-600">{rest}</span>
                </div>
              );
            })}
          </div>
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
