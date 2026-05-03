"""Graph Extractor Agent — extracts characters, events, items and their relationships from chapter text."""

import json
import logging
import re

from app.models.schemas import GraphEdge, GraphNode, GraphUpdate
from app.services.llm import chat, strip_thinking_tags

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是一位专业的文本分析师。你的任务是从给定的小说章节文本中提取三类实体：人物角色、关键事件、重要物品，以及它们之间的关系。

输出要求 — 严格按照以下 JSON 格式，不要输出任何其他内容：
{
  "nodes": [
    {"id": "实体唯一标识", "label": "实体显示名称", "type": "character/event/item", "properties": {...}}
  ],
  "edges": [
    {"source": "源实体ID", "target": "目标实体ID", "relation": "关系类型", "type": "relation/participates/possesses/triggers/appears_in", "properties": {...}}
  ]
}

节点类型及 properties 规范：

1. character（人物）：
   - properties: {"role": "主角/配角/反派", "description": "一句话描述"}

2. event（关键事件）：
   - properties: {"time": "发生时间/章节", "location": "地点", "significance": "重要性（高/中/低）", "participants": "参与人物，逗号分隔"}

3. item（重要物品/道具）：
   - properties: {"category": "武器/信物/法宝/文件/其他", "owner": "持有者", "description": "一句话描述"}

边类型规范：
- relation: 人物间关系（师徒、父子、恋人、宿敌、盟友、上下级、同门、兄弟等）
- participates: 人物参与事件（source=人物, target=事件）
- possesses: 人物持有物品（source=人物, target=物品）
- triggers: 事件触发事件（source=原因事件, target=结果事件）
- appears_in: 物品出现在事件中（source=物品, target=事件）

规则：
- id 使用唯一且一致的标识（人物用姓名，事件用简短描述性ID如"第1章_相遇"，物品用名称）
- 只提取本章中明确出现或提及的实体
- 如果本章没有某类实体，对应数组留空
- properties.role 只有首次出现的人物才需要填写
- 只输出 JSON，不要输出 markdown 代码块标记
"""


def _extract_json(text: str) -> dict | None:
    """Parse JSON from LLM output, stripping thinking blocks and markdown fences."""
    cleaned = strip_thinking_tags(text)
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned)
    cleaned = cleaned.replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    logger.warning("Extractor JSON parse failed. Cleaned text (first 300 chars): %s", cleaned[:300])
    return None


async def extract_graph(chapter_text: str, chapter_number: int) -> GraphUpdate:
    """Analyse chapter text and return structured graph data."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"以下是第{chapter_number}章的内容，请提取人物、事件、物品与关系：\n\n{chapter_text}"},
    ]

    raw = await chat(messages, temperature=0.2, max_tokens=2048, think=False)
    parsed = _extract_json(raw)

    if parsed is None:
        logger.warning("Extractor failed to parse JSON from chapter %d", chapter_number)
        return GraphUpdate()

    nodes = [
        GraphNode(
            id=n.get("id", n.get("label", "")),
            label=n.get("label", n.get("id", "")),
            type=n.get("type", "character"),
            properties=n.get("properties", {}),
        )
        for n in parsed.get("nodes", [])
        if n.get("id") or n.get("label")
    ]
    edges = [
        GraphEdge(
            source=e["source"],
            target=e["target"],
            relation=e.get("relation", "相关"),
            type=e.get("type", "relation"),
            properties=e.get("properties", {}),
        )
        for e in parsed.get("edges", [])
        if e.get("source") and e.get("target")
    ]

    return GraphUpdate(nodes=nodes, edges=edges)
