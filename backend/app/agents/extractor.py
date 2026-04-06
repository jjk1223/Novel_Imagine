"""Graph Extractor Agent — extracts character entities and relationships from chapter text."""

import json
import logging
import re

from app.models.schemas import GraphEdge, GraphNode, GraphUpdate
from app.services.llm import chat, strip_thinking_tags

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是一位专业的文本分析师。你的任务是从给定的小说章节文本中提取所有出现的人物角色及其相互关系。

输出要求 — 严格按照以下 JSON 格式，不要输出任何其他内容：
```json
{
  "nodes": [
    {"id": "人物姓名", "label": "人物姓名", "properties": {"role": "主角/配角/反派", "description": "一句话描述"}}
  ],
  "edges": [
    {"source": "人物A姓名", "target": "人物B姓名", "relation": "关系类型", "properties": {"detail": "关系补充说明"}}
  ]
}
```

规则：
- id 和 label 使用人物的完整姓名（保持全文统一）。
- relation 使用简短的中文关系标签，如：师徒、父子、恋人、宿敌、盟友、上下级、同门、兄弟等。
- 如果本章没有出现新人物或新关系，对应数组留空。
- properties.role 只有首次出现的人物才需要填写。
- 只输出 JSON，不要输出 markdown 代码块标记。
"""


def _extract_json(text: str) -> dict | None:
    """Parse JSON from LLM output, stripping <think> blocks and markdown fences."""
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
        {"role": "user", "content": f"以下是第{chapter_number}章的内容，请提取人物与关系：\n\n{chapter_text}"},
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
            properties=e.get("properties", {}),
        )
        for e in parsed.get("edges", [])
        if e.get("source") and e.get("target")
    ]

    return GraphUpdate(nodes=nodes, edges=edges)
