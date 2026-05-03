"""Writer Agent — writes a single chapter in streaming fashion with rich structured context."""

import json
import logging
import re
from typing import AsyncGenerator

from app.models.schemas import StructuredSummary
from app.services.llm import chat, stream_chat, strip_thinking_tags

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是一位才华横溢的小说家，擅长根据详细的企划书进行高质量创作。

你将根据提供的完整小说企划（包括世界观、角色档案、关系网络、行文风格指导和章节大纲），撰写小说的某一个章节。

写作要求：
- 严格遵循行文风格指导中的叙事视角、语言风格和情感基调
- 每章正文不少于 1500 字，包含丰富的场景描写、人物对话和心理活动
- 严格遵循角色档案中的性格设定、动机和人物弧光，确保角色行为合理一致
- 尊重角色关系网络中描述的关系动态，通过细节体现关系的张力
- 世界观的细节应自然融入叙事，不要生硬地堆砌设定
- 章节开头自然承接前文，结尾留有悬念或情感钩子
- 注意保持文风和叙事节奏的一致性
- 如果提供了【审校意见】，请根据意见修改写作内容，解决指出的问题
- 直接输出章节正文，不要输出章节标题或任何元数据
"""


# ── Tiered memory compiler ──────────────────────────────────

def compile_tiered_memory(
    structured_summaries: list[StructuredSummary],
    chapter_numbers: list[int],
) -> str:
    """Compile structured summaries into a tiered memory context string.

    Instead of passing N plain-text summaries verbatim, this function
    distills them into organized sections that are more useful to the
    writer while staying bounded in size.
    """
    if not structured_summaries:
        return ""

    parts = []

    # Section 1: Plot progression timeline
    plot_lines = []
    for ss, ch_num in zip(structured_summaries, chapter_numbers):
        if ss.plot_progress:
            plot_lines.append(f"  第{ch_num}章：{ss.plot_progress}")
    if plot_lines:
        parts.append("【前文主线进度】\n" + "\n".join(plot_lines))

    # Section 2: Character changes (deduplicated, latest state)
    all_changes = []
    for ss, ch_num in zip(structured_summaries, chapter_numbers):
        if ss.character_changes:
            all_changes.append(f"  第{ch_num}章：{ss.character_changes}")
    if all_changes:
        parts.append("【人物变化追踪】\n" + "\n".join(all_changes))

    # Section 3: Key events (condensed list)
    all_events = []
    for ss, ch_num in zip(structured_summaries, chapter_numbers):
        if ss.key_events:
            all_events.append(f"  第{ch_num}章：{ss.key_events}")
    if all_events:
        parts.append("【关键事件记录】\n" + "\n".join(all_events))

    # Section 4: Active foreshadowing (most important for continuity)
    all_foreshadow = []
    for ss, ch_num in zip(structured_summaries, chapter_numbers):
        if ss.foreshadowing:
            all_foreshadow.append(f"  第{ch_num}章伏笔：{ss.foreshadowing}")
    if all_foreshadow:
        parts.append("【待回收伏笔】\n" + "\n".join(all_foreshadow))

    return "\n".join(parts)


# ── Context builder ─────────────────────────────────────────

def _build_context(
    novel_title: str,
    outline: str,
    chapter_title: str,
    chapter_brief: str,
    chapter_number: int,
    total_chapters: int,
    tiered_memory: str = "",
    character_context: str = "",
    recent_full_texts: list[str] | None = None,
    world_building: str = "",
    main_characters_text: str = "",
    character_relationships: str = "",
    writing_style: str = "",
    reflect_feedback: str = "",
) -> str:
    parts = [f"小说标题：《{novel_title}》"]

    # Tier 1: Core settings (always retained)
    if world_building:
        parts.append(f"\n【世界观与背景设定】\n{world_building}")

    if main_characters_text:
        parts.append(f"\n【角色档案】\n{main_characters_text}")

    if character_relationships:
        parts.append(f"\n【人物关系网络】\n{character_relationships}")

    if writing_style:
        parts.append(f"\n【行文风格指导】\n{writing_style}")

    parts.append(f"\n【主线剧情摘要】\n{outline}")

    if character_context:
        parts.append(f"\n{character_context}")

    # Tier 2: Structured memory (bounded, organized by dimension)
    if tiered_memory:
        parts.append(f"\n{tiered_memory}")

    # Tier 3: Recent full texts (style reference, sliding window)
    if recent_full_texts:
        start_ch = chapter_number - len(recent_full_texts)
        for i, text in enumerate(recent_full_texts):
            ch_n = start_ch + i
            truncated = text[:2000] + "…" if len(text) > 2000 else text
            parts.append(f"\n【第{ch_n}章近期全文（供文风参考）】\n{truncated}")

    # Reflect feedback (if chapter is being rewritten)
    if reflect_feedback:
        parts.append(f"\n【审校意见】\n{reflect_feedback}")

    parts.append(f"\n当前任务：撰写第 {chapter_number}/{total_chapters} 章「{chapter_title}」")
    parts.append(f"本章详细大纲：{chapter_brief}")

    return "\n".join(parts)


def format_characters_for_prompt(main_characters: list[dict]) -> str:
    """Format structured character profiles into readable prompt text."""
    if not main_characters:
        return ""
    lines = []
    for ch in main_characters:
        name = ch.get("name", "未知")
        role = ch.get("role", "")
        desc = ch.get("description", "")
        lines.append(f"▸ {name}（{role}）\n  {desc}")
    return "\n".join(lines)


async def write_chapter_stream(
    novel_title: str,
    outline: str,
    chapter_title: str,
    chapter_brief: str,
    chapter_number: int,
    total_chapters: int,
    tiered_memory: str = "",
    character_context: str = "",
    recent_full_texts: list[str] | None = None,
    world_building: str = "",
    main_characters_text: str = "",
    character_relationships: str = "",
    writing_style: str = "",
    reflect_feedback: str = "",
) -> AsyncGenerator[str, None]:
    """Stream the chapter text token by token."""
    context = _build_context(
        novel_title=novel_title,
        outline=outline,
        chapter_title=chapter_title,
        chapter_brief=chapter_brief,
        chapter_number=chapter_number,
        total_chapters=total_chapters,
        tiered_memory=tiered_memory,
        character_context=character_context,
        recent_full_texts=recent_full_texts,
        world_building=world_building,
        main_characters_text=main_characters_text,
        character_relationships=character_relationships,
        writing_style=writing_style,
        reflect_feedback=reflect_feedback,
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]
    async for chunk in stream_chat(messages, temperature=0.8, max_tokens=8192, filter_thinking=True):
        yield chunk


# ── Structured summary ──────────────────────────────────────

STRUCTURED_SUMMARIZE_PROMPT = """\
请分析以下章节内容，输出结构化的章节摘要。严格按照以下 JSON 格式输出，不要输出任何其他内容：
{{
  "plot_progress": "主线剧情进度（50-100字，描述本章对主线剧情的推进）",
  "character_changes": "人物关系变化（50-100字，包括新增人物、关系变化、角色状态变化）",
  "key_events": "关键事件（列出本章发生的2-5个关键事件，每个事件15-30字）",
  "foreshadowing": "伏笔埋设（列出本章埋下的伏笔或悬念，如无则留空字符串）"
}}

规则：
- 只输出 JSON，不要输出 markdown 代码块标记
- 所有内容必须基于章节文本，不要推测或编造
- key_events 和 foreshadowing 可以是字符串

章节内容：
{content}
"""


def _extract_json(text: str) -> dict | None:
    """Try to parse JSON from LLM output, tolerating markdown fences and thinking blocks."""
    cleaned = strip_thinking_tags(text)
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned)
    cleaned = cleaned.replace("```", "").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Greedy: find outermost { ... }
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Structured summary JSON parse failed. Cleaned text (first 300 chars): %s", cleaned[:300])
    return None


async def summarize_chapter_structured(content: str, chapter_number: int) -> StructuredSummary:
    """Generate a structured summary of a completed chapter."""
    messages = [
        {"role": "user", "content": STRUCTURED_SUMMARIZE_PROMPT.format(content=content)},
    ]
    raw = await chat(messages, temperature=0.2, max_tokens=1024, think=False)
    parsed = _extract_json(raw)

    if parsed is not None:
        try:
            return StructuredSummary(**parsed)
        except Exception as e:
            logger.warning("Structured summary model validation failed: %s", e)

    # Fallback: create minimal summary from raw text
    logger.warning("Falling back to minimal structured summary for chapter %d", chapter_number)
    return StructuredSummary(plot_progress=raw[:150] if raw else "")


def derive_plain_summary(structured: StructuredSummary, chapter_number: int) -> str:
    """Derive a plain-text summary from structured summary for backward compatibility."""
    parts = [f"第{chapter_number}章：{structured.plot_progress}"]
    if structured.key_events:
        parts.append(f"关键事件：{structured.key_events}")
    return "；".join(parts)[:200]
