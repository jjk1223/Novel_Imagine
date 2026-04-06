"""Neo4j graph service — MERGE nodes/edges, query graph, and produce LLM context."""

import logging

from app.database.neo4j import get_driver
from app.models.schemas import GraphEdge, GraphNode, GraphUpdate

logger = logging.getLogger(__name__)


async def merge_graph(novel_id: int, update: GraphUpdate, chapter_number: int = 0) -> None:
    """MERGE nodes and relationships into Neo4j for a given novel.

    Tracks first_appear chapter and updates character status/description
    incrementally without overwriting richer earlier data.
    """
    driver = get_driver()
    if driver is None:
        logger.warning("Neo4j driver unavailable — skipping graph merge")
        return

    async with driver.session() as session:
        for node in update.nodes:
            await session.run(
                """
                MERGE (c:Character {id: $id, novel_id: $novel_id})
                ON CREATE SET
                    c.label = $label,
                    c.role = $role,
                    c.description = $description,
                    c.first_appear = $chapter,
                    c.status = '活跃'
                ON MATCH SET
                    c.description = CASE
                        WHEN $description <> '' THEN $description
                        ELSE c.description END,
                    c.role = CASE
                        WHEN $role <> '' THEN $role
                        ELSE c.role END,
                    c.last_appear = $chapter
                """,
                id=node.id,
                novel_id=novel_id,
                label=node.label,
                role=node.properties.get("role", ""),
                description=node.properties.get("description", ""),
                chapter=chapter_number,
            )

        for edge in update.edges:
            await session.run(
                """
                MATCH (a:Character {id: $source, novel_id: $novel_id})
                MATCH (b:Character {id: $target, novel_id: $novel_id})
                MERGE (a)-[r:RELATION {type: $relation}]->(b)
                ON CREATE SET r.since_chapter = $chapter, r.detail = $detail
                ON MATCH SET r.detail = CASE
                    WHEN $detail <> '' THEN $detail ELSE r.detail END
                """,
                source=edge.source,
                target=edge.target,
                novel_id=novel_id,
                relation=edge.relation,
                detail=edge.properties.get("detail", ""),
                chapter=chapter_number,
            )

    logger.info(
        "Merged %d nodes, %d edges for novel %d (chapter %d)",
        len(update.nodes), len(update.edges), novel_id, chapter_number,
    )


async def query_full_graph(novel_id: int) -> GraphUpdate:
    """Return the full character graph for a novel."""
    driver = get_driver()
    if driver is None:
        return GraphUpdate()

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Character {novel_id: $novel_id}) RETURN c",
            novel_id=novel_id,
        )
        async for record in result:
            c = record["c"]
            nodes.append(GraphNode(
                id=c["id"],
                label=c.get("label", c["id"]),
                properties={
                    "role": c.get("role", ""),
                    "description": c.get("description", ""),
                    "status": c.get("status", ""),
                    "first_appear": str(c.get("first_appear", "")),
                },
            ))

        result = await session.run(
            """
            MATCH (a:Character {novel_id: $novel_id})-[r:RELATION]->(b:Character {novel_id: $novel_id})
            RETURN a.id AS source, b.id AS target, r.type AS relation,
                   r.detail AS detail, r.since_chapter AS since
            """,
            novel_id=novel_id,
        )
        async for record in result:
            edges.append(GraphEdge(
                source=record["source"],
                target=record["target"],
                relation=record["relation"] or "相关",
                properties={
                    "detail": record.get("detail", "") or "",
                    "since_chapter": str(record.get("since", "")),
                },
            ))

    return GraphUpdate(nodes=nodes, edges=edges)


async def get_character_context(novel_id: int, chapter_brief: str = "") -> str:
    """Produce a detailed character-relationship context string for the Writer Agent.

    This is the core GraphRAG function: it queries Neo4j for all characters
    and relationships in this novel and formats them as structured LLM context.
    """
    graph = await query_full_graph(novel_id)
    if not graph.nodes:
        return ""

    lines = ["【当前人物档案】"]
    for n in graph.nodes:
        desc = n.properties.get("description", "")
        role = n.properties.get("role", "")
        status = n.properties.get("status", "")
        first = n.properties.get("first_appear", "")
        tag_parts = [p for p in [role, status] if p]
        tag = f"（{'，'.join(tag_parts)}）" if tag_parts else ""
        appear = f"，首次出场于第{first}章" if first else ""
        lines.append(f"  - {n.label}{tag}：{desc}{appear}")

    if graph.edges:
        lines.append("\n【人物关系网络】")
        for e in graph.edges:
            detail = e.properties.get("detail", "")
            since = e.properties.get("since_chapter", "")
            suffix_parts = []
            if detail:
                suffix_parts.append(detail)
            if since:
                suffix_parts.append(f"始于第{since}章")
            suffix = f"（{'，'.join(suffix_parts)}）" if suffix_parts else ""
            lines.append(f"  - {e.source} —[{e.relation}]→ {e.target}{suffix}")

    lines.append(
        "\n【重要】请严格遵循上述人物设定和关系，不要出现人物性格矛盾或关系错乱。"
        "如果本章有新人物出场或关系变化，请自然地在文中体现。"
    )

    return "\n".join(lines)
