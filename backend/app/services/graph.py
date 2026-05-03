"""Neo4j graph service — MERGE nodes/edges, query graph, and produce LLM context.

Supports three node types: Character, Event, Item.
Supports five edge types: RELATION, PARTICIPATES, POSSESSES, TRIGGERS, APPEARS_IN.
"""

import logging

from app.database.neo4j import get_driver
from app.models.schemas import GraphEdge, GraphNode, GraphUpdate

logger = logging.getLogger(__name__)

# ── Type mapping for Cypher label resolution ─────────────────

_SOURCE_TYPE_MAP = {
    "relation": "Character",
    "participates": "Character",
    "possesses": "Character",
    "triggers": "Event",
    "appears_in": "Item",
}

_TARGET_TYPE_MAP = {
    "relation": "Character",
    "participates": "Event",
    "possesses": "Item",
    "triggers": "Event",
    "appears_in": "Event",
}

_EDGE_LABEL_MAP = {
    "relation": "RELATION",
    "participates": "PARTICIPATES",
    "possesses": "POSSESSES",
    "triggers": "TRIGGERS",
    "appears_in": "APPEARS_IN",
}


async def merge_graph(novel_id: int, update: GraphUpdate, chapter_number: int = 0) -> None:
    """MERGE nodes and relationships into Neo4j for a given novel.

    Supports Character, Event, Item node types and multiple edge types.
    """
    driver = get_driver()
    if driver is None:
        logger.warning("Neo4j driver unavailable — skipping graph merge")
        return

    async with driver.session() as session:
        for node in update.nodes:
            node_type = node.type or "character"

            if node_type == "character":
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
            elif node_type == "event":
                await session.run(
                    """
                    MERGE (e:Event {id: $id, novel_id: $novel_id})
                    ON CREATE SET
                        e.label = $label, e.time = $time,
                        e.location = $location, e.significance = $significance,
                        e.participants = $participants, e.first_appear = $chapter
                    ON MATCH SET
                        e.time = CASE WHEN $time <> '' THEN $time ELSE e.time END,
                        e.location = CASE WHEN $location <> '' THEN $location ELSE e.location END,
                        e.participants = CASE WHEN $participants <> '' THEN $participants ELSE e.participants END,
                        e.last_appear = $chapter
                    """,
                    id=node.id,
                    novel_id=novel_id,
                    label=node.label,
                    time=node.properties.get("time", ""),
                    location=node.properties.get("location", ""),
                    significance=node.properties.get("significance", ""),
                    participants=node.properties.get("participants", ""),
                    chapter=chapter_number,
                )
            elif node_type == "item":
                await session.run(
                    """
                    MERGE (i:Item {id: $id, novel_id: $novel_id})
                    ON CREATE SET
                        i.label = $label, i.category = $category,
                        i.owner = $owner, i.description = $description,
                        i.first_appear = $chapter
                    ON MATCH SET
                        i.owner = CASE
                            WHEN $owner <> '' THEN $owner ELSE i.owner END,
                        i.last_appear = $chapter
                    """,
                    id=node.id,
                    novel_id=novel_id,
                    label=node.label,
                    category=node.properties.get("category", ""),
                    owner=node.properties.get("owner", ""),
                    description=node.properties.get("description", ""),
                    chapter=chapter_number,
                )

        for edge in update.edges:
            edge_type = edge.type or "relation"
            source_label = _SOURCE_TYPE_MAP.get(edge_type, "Character")
            target_label = _TARGET_TYPE_MAP.get(edge_type, "Character")
            rel_label = _EDGE_LABEL_MAP.get(edge_type, "RELATION")

            # f-string for labels is safe: values come from a fixed mapping dict
            await session.run(
                f"""
                MATCH (a:{source_label} {{id: $source, novel_id: $novel_id}})
                MATCH (b:{target_label} {{id: $target, novel_id: $novel_id}})
                MERGE (a)-[r:{rel_label} {{type: $relation}}]->(b)
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
    """Return the full graph for a novel (all node types and edge types)."""
    driver = get_driver()
    if driver is None:
        return GraphUpdate()

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    async with driver.session() as session:
        # Query Character nodes
        result = await session.run(
            "MATCH (c:Character {novel_id: $novel_id}) RETURN c",
            novel_id=novel_id,
        )
        async for record in result:
            c = record["c"]
            nodes.append(GraphNode(
                id=c["id"],
                label=c.get("label", c["id"]),
                type="character",
                properties={
                    "role": c.get("role", ""),
                    "description": c.get("description", ""),
                    "status": c.get("status", ""),
                    "first_appear": str(c.get("first_appear", "")),
                },
            ))

        # Query Event nodes
        result = await session.run(
            "MATCH (e:Event {novel_id: $novel_id}) RETURN e",
            novel_id=novel_id,
        )
        async for record in result:
            e = record["e"]
            nodes.append(GraphNode(
                id=e["id"],
                label=e.get("label", e["id"]),
                type="event",
                properties={
                    "time": e.get("time", ""),
                    "location": e.get("location", ""),
                    "significance": e.get("significance", ""),
                    "participants": e.get("participants", ""),
                },
            ))

        # Query Item nodes
        result = await session.run(
            "MATCH (i:Item {novel_id: $novel_id}) RETURN i",
            novel_id=novel_id,
        )
        async for record in result:
            i = record["i"]
            nodes.append(GraphNode(
                id=i["id"],
                label=i.get("label", i["id"]),
                type="item",
                properties={
                    "category": i.get("category", ""),
                    "owner": i.get("owner", ""),
                    "description": i.get("description", ""),
                },
            ))

        # Query all relationship types (skip types that don't exist yet in the DB)
        for rel_label in ["RELATION", "PARTICIPATES", "POSSESSES", "TRIGGERS", "APPEARS_IN"]:
            try:
                result = await session.run(
                    f"MATCH (a)-[r:{rel_label}]-(b) "
                    f"WHERE a.novel_id = $novel_id AND b.novel_id = $novel_id "
                    f"RETURN a.id AS source, b.id AS target, "
                    f"r.type AS relation, r.detail AS detail, r.since_chapter AS since",
                    novel_id=novel_id,
                )
                async for record in result:
                    edges.append(GraphEdge(
                        source=record["source"],
                        target=record["target"],
                        relation=record["relation"] or rel_label.lower(),
                        type=rel_label.lower(),
                        properties={
                            "detail": record.get("detail", "") or "",
                            "since_chapter": str(record.get("since", "")),
                        },
                    ))
            except Exception as e:
                # Relationship type may not exist yet in the database
                if "missing relationship type" in str(e).lower() or "does not exist" in str(e).lower():
                    logger.debug("Skipping non-existent relationship type: %s", rel_label)
                else:
                    logger.warning("Failed to query relationship type %s: %s", rel_label, e)

    # Deduplicate edges (undirected queries may return duplicates)
    seen: set[tuple[str, str, str, str]] = set()
    unique_edges: list[GraphEdge] = []
    for e in edges:
        key = (e.source, e.target, e.type, e.relation)
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)

    return GraphUpdate(nodes=nodes, edges=unique_edges)


async def get_character_context(novel_id: int, chapter_brief: str = "") -> str:
    """Produce a detailed context string for the Writer Agent from the full graph.

    Includes character profiles, event records, items, relationships,
    and cross-type associations.
    """
    graph = await query_full_graph(novel_id)
    if not graph.nodes:
        return ""

    lines = ["【当前人物档案】"]
    for n in graph.nodes:
        if n.type != "character":
            continue
        desc = n.properties.get("description", "")
        role = n.properties.get("role", "")
        status = n.properties.get("status", "")
        first = n.properties.get("first_appear", "")
        tag_parts = [p for p in [role, status] if p]
        tag = f"（{'，'.join(tag_parts)}）" if tag_parts else ""
        appear = f"，首次出场于第{first}章" if first else ""
        lines.append(f"  - {n.label}{tag}：{desc}{appear}")

    # Event context
    events = [n for n in graph.nodes if n.type == "event"]
    if events:
        lines.append("\n【关键事件记录】")
        for n in events:
            time = n.properties.get("time", "")
            loc = n.properties.get("location", "")
            sig = n.properties.get("significance", "")
            participants = n.properties.get("participants", "")
            parts = [p for p in [time, loc, f"重要性：{sig}"] if p]
            detail = f"（{'，'.join(parts)}）" if parts else ""
            lines.append(f"  - {n.label}{detail}")
            if participants:
                lines.append(f"    参与者：{participants}")

    # Item context
    items = [n for n in graph.nodes if n.type == "item"]
    if items:
        lines.append("\n【重要物品】")
        for n in items:
            owner = n.properties.get("owner", "")
            cat = n.properties.get("category", "")
            desc = n.properties.get("description", "")
            parts = [p for p in [cat, f"持有者：{owner}"] if p]
            tag = f"（{'，'.join(parts)}）" if parts else ""
            lines.append(f"  - {n.label}{tag}：{desc}")

    # Character-to-character relationships
    char_edges = [e for e in graph.edges if e.type == "relation"]
    if char_edges:
        lines.append("\n【人物关系网络】")
        for e in char_edges:
            detail = e.properties.get("detail", "")
            since = e.properties.get("since_chapter", "")
            suffix_parts = []
            if detail:
                suffix_parts.append(detail)
            if since:
                suffix_parts.append(f"始于第{since}章")
            suffix = f"（{'，'.join(suffix_parts)}）" if suffix_parts else ""
            lines.append(f"  - {e.source} —[{e.relation}]→ {e.target}{suffix}")

    # Cross-type edges
    cross_edges = [e for e in graph.edges if e.type != "relation"]
    if cross_edges:
        lines.append("\n【人物-事件-物品关联】")
        for e in cross_edges:
            detail = e.properties.get("detail", "")
            suffix = f"（{detail}）" if detail else ""
            lines.append(f"  - {e.source} —[{e.relation}]→ {e.target}{suffix}")

    lines.append(
        "\n【重要】请严格遵循上述人物设定和关系，不要出现人物性格矛盾或关系错乱。"
        "如涉及已知事件或物品，请保持一致性。"
    )

    return "\n".join(lines)
