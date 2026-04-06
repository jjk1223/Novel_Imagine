"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchHealth, type HealthStatus } from "@/lib/api";
import { useNovelGeneration } from "@/lib/useNovelGeneration";
import ConfigPanel from "@/components/ConfigPanel";
import NovelPanel from "@/components/NovelPanel";
import GraphPanel from "@/components/GraphPanel";
import HistoryPanel from "@/components/HistoryPanel";

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : "bg-red-400"}`} />
  );
}

function HealthBar({ health }: { health: HealthStatus | null }) {
  if (!health) return <span className="text-xs text-slate-400">Connecting…</span>;
  const items = [
    { label: "SQLite", value: health.sqlite },
    { label: "Neo4j", value: health.neo4j },
    { label: "LLM", value: health.llm },
  ];
  return (
    <div className="flex items-center gap-4 text-xs text-slate-500">
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-1.5">
          <StatusDot ok={it.value === "ok"} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

export default function Home() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const {
    state, setProvider, plan, updateOutline, confirmAndGenerate, resume, stop, reset,
  } = useNovelGeneration();

  const checkHealth = useCallback(async () => {
    try { setHealth(await fetchHealth()); } catch { setHealth(null); }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30_000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  const handleResume = useCallback((novelId: number) => {
    setShowHistory(false);
    resume(novelId);
  }, [resume]);

  return (
    <div className="flex h-screen flex-col">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold tracking-tight text-slate-900">
            Novel Imagine
          </h1>
          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-600">
            AI 创作
          </span>
        </div>
        <HealthBar health={health} />
      </header>

      <div className="flex min-h-0 flex-1">
        <ConfigPanel
          state={state}
          onPlan={plan}
          onSetProvider={setProvider}
          onStop={stop}
          onReset={reset}
          onShowHistory={() => setShowHistory(true)}
        />
        <NovelPanel
          state={state}
          onUpdateOutline={updateOutline}
          onConfirmGenerate={confirmAndGenerate}
          onReset={reset}
          onResume={handleResume}
        />
        <GraphPanel graph={state.graph} />
      </div>

      {state.error && state.phase !== "error" && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-lg border border-red-200 bg-red-50 px-5 py-3 shadow-lg">
          <p className="text-sm text-red-700">{state.error}</p>
        </div>
      )}

      {showHistory && (
        <HistoryPanel
          onClose={() => setShowHistory(false)}
          onResume={handleResume}
        />
      )}
    </div>
  );
}
