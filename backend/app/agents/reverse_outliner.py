"""Reverse Outline Agent — periodically optimizes the remaining outline based on actual written content."""

import json
import logging
import re

from app.models.schemas import ChapterOutline, ReverseOutlineResult
from app.services.llm import chat, strip_thinking_tags

logger = logging.getLogger(__name__)

REVERSE_OUTLINE_SYSTEM_PROMPT = """\
你是一位经验丰富的小说结构编辑。你的任务是基于已完成章节的实际内容，对比原始大纲，为后续章节提供修正建议。

你需要：
1. 分析已完成章节的剧情走向、人物发展和伏笔设置
2. 对比原始大纲，找出偏差和需要调整的地方
3. 为后续章节生成修正后的大纲，确保：
   - 与已完成内容自然衔接
   - 保留已埋伏笔的回收计划
   - 适应人物关系的新变化
   - 保持整体叙事节奏

输出格式 — 严格按照以下 JSON 格式输出，不要输出任何其他内容：
{
  "analysis": "偏差分析（100-200字，描述实际内容与大纲的偏差及原因）",
  "outline_updates": {
    "character_relationships": "更新后的人物关系描述（如有变化，否则留空字符串）",
    "outline": "更新后的主线摘要（如有变化，否则留空字符串）"
  },
  "updated_chapters_remaining": [
    {"chapter_number": N, "title": "章节标题", "brief": "修正后的章节概要（150-300字）"}
  ]
}

规则：
- 只修改后续章节的大纲，不要修改已完成章节
- 如果实际走向优于原大纲，应该顺应实际走向
- 保持后续章节数量不变
- updated_chapters_remaining 数组中只需包含需要修改的章节，不需要修改的可省略
- 只输出 JSON，不要输出 markdown 代码块标记
"""


def _extract_json(text: str) -> dict | None:
    """Try to parse JSON from LLM output."""
    cleaned = strip_thinking_tags(text)
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned)
    cleaned = cleaned.replace("```", "").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Balanced-brace extraction
    for start in range(len(cleaned)):
        if cleaned[start] == "{":
            depth = 0
            for end in range(start, len(cleaned)):
                if cleaned[end] == "{":
                    depth += 1
                elif cleaned[end] == "}":
                    depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start : end + 1])
                    except json.JSONDecodeError:
                        break
            break

    logger.warning("Reverse outline JSON parse failed. Cleaned text (first 300 chars): %s", cleaned[:300])
    return None


async def run_reverse_outline(
    written_chapters_text: str,
    original_outline: str,
    original_chapters: list[dict],
    character_relationships: str,
    world_building: str,
    completed_count: int,
    total_count: int,
) -> ReverseOutlineResult:
    """Compare written chapters against the original outline and suggest corrections."""

    remaining_briefs = "\n".join(
        f"  第{ch['chapter_number']}章「{ch['title']}」：{ch['brief']}"
        for ch in original_chapters
    )

    user_content = (
        f"【已完成章节的结构化记忆】\n{written_chapters_text}\n\n"
        f"【原始主线剧情摘要】\n{original_outline}\n\n"
        f"【原始人物关系】\n{character_relationships}\n\n"
        f"【世界观设定】\n{world_building}\n\n"
        f"【后续章节原始大纲】（已完成 {completed_count}/{total_count} 章）\n"
        f"{remaining_briefs}\n\n"
        f"请基于已完成内容的实际走向，为后续章节提供修正建议。"
    )

    messages = [
        {"role": "system", "content": REVERSE_OUTLINE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    raw = await chat(messages, temperature=0.4, max_tokens=4096, think=False)
    parsed = _extract_json(raw)

    if parsed is not None:
        try:
            # Parse updated_chapters_remaining into ChapterOutline objects
            updated_chapters = []
            for ch_data in parsed.get("updated_chapters_remaining", []):
                try:
                    updated_chapters.append(ChapterOutline(**ch_data))
                except Exception:
                    logger.warning("Skipping invalid chapter outline in reverse outline result: %s", ch_data)

            return ReverseOutlineResult(
                analysis=parsed.get("analysis", ""),
                outline_updates=parsed.get("outline_updates", {}),
                updated_chapters_remaining=updated_chapters,
            )
        except Exception as e:
            logger.warning("Reverse outline model validation failed: %s", e)

    # Fallback: no updates if parsing fails
    logger.warning("Reverse outline JSON parse failed, returning empty result")
    return ReverseOutlineResult(analysis=raw[:200] if raw else "逆向大纲优化结果解析失败")
