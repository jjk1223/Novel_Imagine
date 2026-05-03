"""Reflect Agent — post-chapter quality check for factual consistency and narrative coherence."""

import json
import logging
import re

from app.models.schemas import ReflectResult
from app.services.llm import chat, strip_thinking_tags

logger = logging.getLogger(__name__)

REFLECT_SYSTEM_PROMPT = """\
你是一位严格的小说编辑审校员。你的任务是审查刚写完的章节，检查是否存在以下问题：

1. 事实矛盾：与世界观设定、前文情节存在矛盾（如角色名错误、地点冲突、设定违背）
2. 人物走形：角色的言行不符合其性格设定和动机（如冷静的人突然暴怒、死者复现）
3. 时间线冲突：事件的发生顺序或时间跨度存在问题
4. 情节断裂：与前文的衔接不自然，或逻辑链断裂
5. 伏笔遗忘：前文埋下的伏笔在本章应有呼应但未出现

输出格式 — 严格按照以下 JSON 格式输出，不要输出任何其他内容：
{
  "issues_found": true或false,
  "issues": ["问题1的具体描述", "问题2的具体描述"],
  "reasoning": "你的审查推理过程（100字以内）"
}

规则：
- 如果章节质量良好，无矛盾问题，issues_found 设为 false，issues 留空数组
- issues 中每个问题应具体指出矛盾之处，而非笼统描述
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

    logger.warning("Reflect JSON parse failed. Cleaned text (first 300 chars): %s", cleaned[:300])
    return None


async def reflect_chapter(
    chapter_text: str,
    chapter_number: int,
    chapter_brief: str,
    world_building: str,
    main_characters_text: str,
    character_relationships: str,
    tiered_memory: str,
    outline: str,
) -> ReflectResult:
    """Review a completed chapter for factual contradictions and narrative issues."""

    # Build the review context
    parts = ["请审校以下章节内容：\n"]

    if world_building:
        parts.append(f"【世界观设定】\n{world_building}\n")

    if main_characters_text:
        parts.append(f"【角色档案】\n{main_characters_text}\n")

    if character_relationships:
        parts.append(f"【人物关系】\n{character_relationships}\n")

    if outline:
        parts.append(f"【主线剧情摘要】\n{outline}\n")

    if tiered_memory:
        parts.append(f"【前文记忆】\n{tiered_memory}\n")

    parts.append(f"【本章大纲】\n{chapter_brief}\n")
    parts.append(f"【第{chapter_number}章正文】\n{chapter_text}")

    messages = [
        {"role": "system", "content": REFLECT_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]

    raw = await chat(messages, temperature=0.2, max_tokens=1024, think=False)
    parsed = _extract_json(raw)

    if parsed is not None:
        try:
            return ReflectResult(**parsed)
        except Exception as e:
            logger.warning("Reflect model validation failed: %s", e)

    # Fallback: assume no issues if parsing fails
    logger.warning("Reflect JSON parse failed for chapter %d, assuming no issues", chapter_number)
    return ReflectResult(reasoning=raw[:200] if raw else "审校结果解析失败")
