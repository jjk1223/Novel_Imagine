"use client";

import { useState } from "react";
import type { OutlineData, CharacterProfile, ChapterOutline } from "@/lib/api";

interface Props {
  outline: OutlineData;
  onUpdate: (outline: OutlineData) => void;
  onConfirm: () => void;
  onReset: () => void;
}

type Tab = "overview" | "characters" | "chapters";

const TAB_LABELS: Record<Tab, string> = {
  overview: "总览",
  characters: "角色档案",
  chapters: "分章大纲",
};

export default function OutlineEditor({ outline, onUpdate, onConfirm, onReset }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [editingChapter, setEditingChapter] = useState<number | null>(null);
  const [editingChar, setEditingChar] = useState<number | null>(null);

  function set<K extends keyof OutlineData>(key: K, value: OutlineData[K]) {
    onUpdate({ ...outline, [key]: value });
  }

  function updateCharacter(idx: number, field: keyof CharacterProfile, value: string) {
    const chars = [...(outline.main_characters ?? [])];
    chars[idx] = { ...chars[idx], [field]: value };
    set("main_characters", chars);
  }

  function addCharacter() {
    const chars = [...(outline.main_characters ?? [])];
    chars.push({ name: "新角色", role: "配角", description: "" });
    set("main_characters", chars);
    setEditingChar(chars.length - 1);
  }

  function removeCharacter(idx: number) {
    const chars = [...(outline.main_characters ?? [])];
    chars.splice(idx, 1);
    set("main_characters", chars);
    setEditingChar(null);
  }

  function updateChapter(idx: number, field: keyof ChapterOutline, value: string) {
    const chapters = [...outline.chapters];
    chapters[idx] = { ...chapters[idx], [field]: field === "chapter_number" ? Number(value) : value };
    set("chapters", chapters);
  }

  const inputClass = "w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100";
  const textareaClass = `${inputClass} resize-none leading-relaxed`;
  const labelClass = "mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-400";

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-slate-100 bg-white px-6 py-3">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-semibold text-slate-800">
            《{outline.title}》企划书
          </h2>
          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-600">
            待确认
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onReset}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-500 transition hover:bg-slate-50"
          >
            放弃重来
          </button>
          <button
            onClick={onConfirm}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-indigo-700"
          >
            确认并开始创作
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex shrink-0 gap-0 border-b border-slate-100 bg-white px-6">
        {(Object.keys(TAB_LABELS) as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`border-b-2 px-4 py-2.5 text-xs font-medium transition ${
              activeTab === tab
                ? "border-indigo-500 text-indigo-600"
                : "border-transparent text-slate-400 hover:text-slate-600"
            }`}
          >
            {TAB_LABELS[tab]}
            {tab === "characters" && outline.main_characters?.length
              ? ` (${outline.main_characters.length})`
              : ""}
            {tab === "chapters" ? ` (${outline.chapters.length})` : ""}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="mx-auto max-w-3xl px-8 py-6">
          {activeTab === "overview" && (
            <div className="space-y-5">
              <div>
                <label className={labelClass}>标题</label>
                <input
                  value={outline.title}
                  onChange={(e) => set("title", e.target.value)}
                  className={`${inputClass} text-base font-semibold`}
                />
              </div>

              <div>
                <label className={labelClass}>世界观与背景设定</label>
                <textarea
                  rows={8}
                  value={outline.world_building ?? ""}
                  onChange={(e) => set("world_building", e.target.value)}
                  className={textareaClass}
                  placeholder="时代背景、地理环境、世界体系、关键地点、社会规则…"
                />
              </div>

              <div>
                <label className={labelClass}>人物关系网络</label>
                <textarea
                  rows={5}
                  value={outline.character_relationships ?? ""}
                  onChange={(e) => set("character_relationships", e.target.value)}
                  className={textareaClass}
                  placeholder="角色之间的关系、张力、潜在冲突和演变方向…"
                />
              </div>

              <div>
                <label className={labelClass}>行文风格指导</label>
                <textarea
                  rows={4}
                  value={outline.writing_style ?? ""}
                  onChange={(e) => set("writing_style", e.target.value)}
                  className={textareaClass}
                  placeholder="叙事视角、语言风格、节奏、情感基调、特殊手法…"
                />
              </div>

              <div>
                <label className={labelClass}>主线剧情摘要</label>
                <textarea
                  rows={8}
                  value={outline.outline}
                  onChange={(e) => set("outline", e.target.value)}
                  className={textareaClass}
                  placeholder="起承转合的完整主线概述…"
                />
              </div>
            </div>
          )}

          {activeTab === "characters" && (
            <div className="space-y-3">
              {(outline.main_characters ?? []).map((ch, idx) => (
                <div
                  key={idx}
                  className={`rounded-xl border transition ${
                    editingChar === idx
                      ? "border-indigo-300 bg-indigo-50/50 shadow-sm"
                      : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  {editingChar === idx ? (
                    <div className="space-y-3 p-4">
                      <div className="flex gap-3">
                        <div className="flex-1">
                          <label className={labelClass}>姓名</label>
                          <input
                            value={ch.name}
                            onChange={(e) => updateCharacter(idx, "name", e.target.value)}
                            className={inputClass}
                          />
                        </div>
                        <div className="w-32">
                          <label className={labelClass}>定位</label>
                          <input
                            value={ch.role}
                            onChange={(e) => updateCharacter(idx, "role", e.target.value)}
                            className={inputClass}
                            placeholder="主角/配角/反派"
                          />
                        </div>
                      </div>
                      <div>
                        <label className={labelClass}>详细档案</label>
                        <textarea
                          rows={6}
                          value={ch.description}
                          onChange={(e) => updateCharacter(idx, "description", e.target.value)}
                          className={textareaClass}
                          placeholder="外貌、性格、背景、动机、人物弧光…"
                        />
                      </div>
                      <div className="flex justify-between">
                        <button
                          onClick={() => removeCharacter(idx)}
                          className="text-[11px] font-medium text-red-400 transition hover:text-red-600"
                        >
                          删除角色
                        </button>
                        <button
                          onClick={() => setEditingChar(null)}
                          className="text-[11px] font-medium text-indigo-600 transition hover:text-indigo-800"
                        >
                          收起
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div
                      onClick={() => setEditingChar(idx)}
                      className="cursor-pointer px-4 py-3"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-slate-800">{ch.name}</span>
                        <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                          {ch.role}
                        </span>
                        <span className="ml-auto text-[10px] text-slate-300">点击编辑</span>
                      </div>
                      {ch.description && (
                        <p className="mt-1.5 text-xs leading-relaxed text-slate-500 line-clamp-2">
                          {ch.description}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              ))}

              <button
                onClick={addCharacter}
                className="flex w-full items-center justify-center gap-1.5 rounded-xl border-2 border-dashed border-slate-200 py-3 text-xs font-medium text-slate-400 transition hover:border-indigo-300 hover:text-indigo-500"
              >
                <span className="text-lg leading-none">+</span> 添加角色
              </button>
            </div>
          )}

          {activeTab === "chapters" && (
            <div className="space-y-2">
              {outline.chapters.map((ch, idx) => (
                <div
                  key={ch.chapter_number}
                  className={`rounded-xl border transition ${
                    editingChapter === idx
                      ? "border-indigo-300 bg-indigo-50/50 shadow-sm"
                      : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  {editingChapter === idx ? (
                    <div className="space-y-3 p-4">
                      <div className="flex items-center gap-3">
                        <span className="shrink-0 rounded-lg bg-indigo-100 px-2 py-1 text-xs font-bold text-indigo-600">
                          {String(ch.chapter_number).padStart(2, "0")}
                        </span>
                        <input
                          value={ch.title}
                          onChange={(e) => updateChapter(idx, "title", e.target.value)}
                          className={`${inputClass} font-medium`}
                          placeholder="章节标题"
                        />
                      </div>
                      <div>
                        <label className={labelClass}>详细概要</label>
                        <textarea
                          rows={6}
                          value={ch.brief}
                          onChange={(e) => updateChapter(idx, "brief", e.target.value)}
                          className={textareaClass}
                          placeholder="核心事件、出场角色、情感变化、场景转换、悬念钩子…"
                        />
                      </div>
                      <div className="flex justify-end">
                        <button
                          onClick={() => setEditingChapter(null)}
                          className="text-[11px] font-medium text-indigo-600 transition hover:text-indigo-800"
                        >
                          收起
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div
                      onClick={() => setEditingChapter(idx)}
                      className="cursor-pointer px-4 py-3"
                    >
                      <div className="flex items-center gap-2">
                        <span className="shrink-0 font-mono text-xs font-bold text-slate-300">
                          {String(ch.chapter_number).padStart(2, "0")}
                        </span>
                        <span className="text-sm font-medium text-slate-700">{ch.title}</span>
                        <span className="ml-auto text-[10px] text-slate-300">点击编辑</span>
                      </div>
                      {ch.brief && (
                        <p className="mt-1.5 pl-7 text-xs leading-relaxed text-slate-500 line-clamp-2">
                          {ch.brief}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
