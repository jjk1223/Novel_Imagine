"""Writer Agent — writes a single chapter in streaming fashion with rich structured context."""

import logging
from typing import AsyncGenerator

from app.services.llm import stream_chat

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
- 直接输出章节正文，不要输出章节标题或任何元数据
"""


def _build_context(
    novel_title: str,
    outline: str,
    chapter_title: str,
    chapter_brief: str,
    chapter_number: int,
    total_chapters: int,
    previous_summaries: list[str],
    character_context: str = "",
    recent_full_texts: list[str] | None = None,
    world_building: str = "",
    main_characters_text: str = "",
    character_relationships: str = "",
    writing_style: str = "",
) -> str:
    parts = [f"小说标题：《{novel_title}》"]

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

    if previous_summaries:
        summaries_text = "\n".join(
            f"  第{i+1}章：{s}" for i, s in enumerate(previous_summaries)
        )
        parts.append(f"\n【前文摘要】\n{summaries_text}")

    if recent_full_texts:
        start_ch = chapter_number - len(recent_full_texts)
        for i, text in enumerate(recent_full_texts):
            ch_n = start_ch + i
            truncated = text[:2000] + "…" if len(text) > 2000 else text
            parts.append(f"\n【第{ch_n}章近期全文（供文风参考）】\n{truncated}")

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
    previous_summaries: list[str],
    character_context: str = "",
    recent_full_texts: list[str] | None = None,
    world_building: str = "",
    main_characters_text: str = "",
    character_relationships: str = "",
    writing_style: str = "",
) -> AsyncGenerator[str, None]:
    """Stream the chapter text token by token."""
    context = _build_context(
        novel_title=novel_title,
        outline=outline,
        chapter_title=chapter_title,
        chapter_brief=chapter_brief,
        chapter_number=chapter_number,
        total_chapters=total_chapters,
        previous_summaries=previous_summaries,
        character_context=character_context,
        recent_full_texts=recent_full_texts,
        world_building=world_building,
        main_characters_text=main_characters_text,
        character_relationships=character_relationships,
        writing_style=writing_style,
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]
    async for chunk in stream_chat(messages, temperature=0.8, max_tokens=8192, filter_thinking=True):
        yield chunk


SUMMARIZE_PROMPT = """\
请用 100-150 字概括以下章节的核心情节、出场人物及关键转折。只输出摘要文本。

章节内容：
{content}
"""


async def summarize_chapter(content: str) -> str:
    """Generate a concise summary of a completed chapter."""
    from app.services.llm import chat

    messages = [
        {"role": "user", "content": SUMMARIZE_PROMPT.format(content=content)},
    ]
    return await chat(messages, temperature=0.3, max_tokens=512, think=False)
