"""Planner Agent — expands a user premise into a professional, structured novel outline."""

import json
import logging
import re
from typing import AsyncGenerator

from app.services.llm import chat, stream_chat, strip_thinking_tags

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是一位顶级小说策划编辑，拥有20年类型文学策划经验，精通叙事结构（三幕式、英雄之旅、起承转合）和各类型文学的创作规律。

用户会给你一段故事构思和题材信息。你需要像专业编辑一样，将粗略的构思扩展为一份高质量、可直接用于创作的完整小说企划书。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
你必须完成以下七个维度的规划：

【1. 标题】
- 起一个兼具文学性与吸引力的标题
- 标题应暗示核心冲突或主题，引发好奇

【2. 世界观与背景设定】(world_building)
- 时代背景：故事发生的时间、地域、社会环境
- 如果是架空/奇幻/科幻，需要构建独特的世界体系（力量体系、社会规则、文明形态等）
- 关键地点：主要场景的描述和氛围
- 社会规则：影响剧情走向的核心设定
- 300-500字，务必生动具体，有画面感

【3. 主要角色档案】(main_characters)
为每个重要角色建立档案（至少3个角色）：
- name: 角色姓名
- role: 叙事定位（如：主角、女主、导师、反派、配角等）
- description: 包含以下维度的150-250字详细描述：
  · 外貌特征（年龄、体貌、标志性特点）
  · 性格特质（核心性格 + 性格缺陷）
  · 人生背景（过往经历如何塑造了TA）
  · 核心动机（TA最想要什么？最害怕什么？）
  · 人物弧光（TA将在故事中经历怎样的成长/堕落）

【4. 人物关系网络】(character_relationships)
- 详细描述角色之间的关系（血缘、友情、爱情、师徒、敌对、利用等）
- 指出关系中的张力和潜在冲突点
- 说明关系会如何随剧情演变
- 200-300字

【5. 行文风格指导】(writing_style)
- 叙事视角（第一人称/第三人称有限/全知视角，以谁为焦点）
- 语言风格（华丽、简练、幽默、冷峻、诗意等）
- 叙事节奏（快节奏动作驱动 / 慢节奏心理描写为主 / 交替节奏等）
- 情感基调（热血、压抑、温暖、悬疑紧张等）
- 特殊手法（倒叙、多线叙事、不可靠叙事者等，如无可不填）
- 100-200字

【6. 主线剧情摘要】(outline)
- 用起承转合的结构概括整部小说的主线
- 起：故事开端，主角的日常与打破平衡的事件
- 承：冲突升级，主角面临的挑战和成长
- 转：高潮/转折，核心矛盾的激化
- 合：结局走向（可以留有余韵，但主线需有明确收束）
- 300-500字

【7. 分章大纲】(chapters)
为每一章编写详细大纲：
- title: 有文学感的章节标题（不要简单用"第X章"）
- brief: 150-300字的详细概要，必须包含：
  · 本章核心事件和场景
  · 出场的主要角色及其行动
  · 角色的情感变化和心理状态
  · 与上一章的衔接和本章结尾的悬念/钩子
  · 本章在整体叙事中的功能（铺垫、转折、高潮等）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
全局约束：
- chapters 数组长度必须等于用户要求的章节数
- 确保整体叙事符合起承转合/三幕结构，节奏张弛有度
- 角色行为必须符合其性格设定和动机
- 每章之间必须有清晰的因果链和情节递进
- 主题/母题应贯穿全书，在关键节点呼应

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
严格按照以下 JSON 格式输出，不要输出任何额外文字：
{
  "title": "小说标题",
  "world_building": "世界观与背景设定（300-500字）",
  "main_characters": [
    {"name": "角色名", "role": "叙事定位", "description": "150-250字详细档案"}
  ],
  "character_relationships": "人物关系网络描述（200-300字）",
  "writing_style": "行文风格指导（100-200字）",
  "outline": "主线剧情摘要（300-500字）",
  "chapters": [
    {"chapter_number": 1, "title": "文学性章节标题", "brief": "150-300字详细概要"}
  ]
}
"""


def _build_user_message(premise: str, genre: str, num_chapters: int) -> str:
    return (
        f"【题材类型】{genre}\n"
        f"【目标章节数】{num_chapters}\n"
        f"【我的故事构思】\n{premise}\n\n"
        f"请基于以上构思，生成一份完整的专业小说企划书（JSON 格式）。"
    )


def _extract_json(text: str) -> dict | None:
    """Try to parse JSON from LLM output, tolerating markdown fences and <think> blocks."""
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

    logger.warning("JSON extraction failed. Cleaned text (first 500 chars): %s", cleaned[:500])
    return None


async def run_planner_stream(
    premise: str, genre: str, num_chapters: int
) -> AsyncGenerator[str, None]:
    """Stream the planner output (thinking tokens filtered out)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_message(premise, genre, num_chapters)},
    ]
    async for chunk in stream_chat(messages, temperature=0.7, max_tokens=12000, filter_thinking=True):
        yield chunk


async def run_planner_chat(
    premise: str, genre: str, num_chapters: int
) -> str:
    """Run planner via non-streaming chat (most reliable for JSON extraction)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_message(premise, genre, num_chapters)},
    ]
    return await chat(messages, temperature=0.7, max_tokens=12000, think=False)


async def run_planner(premise: str, genre: str, num_chapters: int) -> dict:
    """Run planner and return parsed JSON result."""
    full_text = await run_planner_chat(premise, genre, num_chapters)

    result = _extract_json(full_text)
    if result is None:
        raise ValueError(f"Planner output is not valid JSON:\n{full_text[:500]}")

    if "chapters" not in result or not isinstance(result["chapters"], list):
        raise ValueError("Planner output missing 'chapters' array")

    return result
