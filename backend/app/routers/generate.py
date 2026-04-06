"""Generation endpoints — plan, generate, and resume."""

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.agents.extractor import extract_graph
from app.agents.planner import run_planner_stream, run_planner_chat, _extract_json
from app.agents.writer import (
    format_characters_for_prompt,
    summarize_chapter,
    write_chapter_stream,
)
from app.database.sqlite import Chapter, Novel, get_db_session
from app.models.schemas import (
    GenerateFromOutlineRequest,
    NovelRequest,
    OutlineResult,
    ResumeRequest,
)
from app.services.graph import get_character_context, merge_graph, query_full_graph
from app.services.llm import set_llm_provider, unload_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generate"])

MAX_PLANNER_RETRIES = 3
RECENT_FULL_TEXT_CHAPTERS = 2


def _sse(event: str, data) -> dict:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return {"event": event, "data": payload}


def _validate_plan(parsed: dict | None) -> bool:
    if not parsed:
        return False
    if "chapters" not in parsed or not isinstance(parsed["chapters"], list):
        return False
    if len(parsed["chapters"]) == 0:
        return False
    return True


# ── POST /api/plan ────────────────────────────────────────────────

async def _plan_pipeline(
    req: NovelRequest, db: AsyncSession
) -> AsyncGenerator[dict, None]:
    try:
        set_llm_provider(req.provider)
        provider_label = "本地 Ollama" if req.provider == "ollama" else "在线 Qwen API"
        yield _sse("status", "正在构思大纲和章节规划…")
        yield _sse("thinking", f"模型：{provider_label}\n收到构思：{req.premise[:80]}…\n题材：{req.genre}，目标 {req.num_chapters} 章")

        plan = None

        for attempt in range(1, MAX_PLANNER_RETRIES + 1):
            if attempt == 1:
                yield _sse("thinking", "[Planner] 第 1 次调用（流式）…")
                planner_text = ""
                async for chunk in run_planner_stream(req.premise, req.genre, req.num_chapters):
                    planner_text += chunk
                    yield _sse("text", chunk)

                parsed = _extract_json(planner_text)
                if _validate_plan(parsed):
                    plan = parsed
                    break

                yield _sse("thinking", "[Planner] 流式输出无法解析，尝试非流式调用…")
                full_text = await run_planner_chat(req.premise, req.genre, req.num_chapters)
                yield _sse("thinking", f"[Planner] 非流式响应（{len(full_text)} 字）")

                parsed = _extract_json(full_text)
                if _validate_plan(parsed):
                    plan = parsed
                    break

                yield _sse("thinking", f"第 {attempt} 次尝试输出无法解析为有效 JSON")
            else:
                yield _sse("thinking", f"大纲解析失败，正在进行第 {attempt} 次重试…")
                yield _sse("status", f"大纲重试中（第 {attempt}/{MAX_PLANNER_RETRIES} 次）…")

                full_text = await run_planner_chat(req.premise, req.genre, req.num_chapters)
                yield _sse("thinking", f"[Planner] 第 {attempt} 次响应（{len(full_text)} 字）")

                parsed = _extract_json(full_text)
                if _validate_plan(parsed):
                    plan = parsed
                    break

                yield _sse("thinking", f"第 {attempt} 次尝试输出无法解析为有效 JSON")

        if plan is None:
            yield _sse("error", f"经过 {MAX_PLANNER_RETRIES} 次尝试，大纲仍无法解析。请重试。")
            return

        title = plan.get("title", "未命名小说")
        chapters_plan = plan.get("chapters", [])

        has_world = bool(plan.get("world_building"))
        has_chars = bool(plan.get("main_characters"))
        has_rels = bool(plan.get("character_relationships"))
        has_style = bool(plan.get("writing_style"))
        richness = sum([has_world, has_chars, has_rels, has_style])

        yield _sse("thinking",
            f"大纲解析成功 → 标题《{title}》，{len(chapters_plan)} 章，"
            f"企划完整度 {richness}/4")

        outline_json = json.dumps(plan, ensure_ascii=False)

        novel = Novel(
            title=title,
            premise=req.premise,
            outline=outline_json,
            status="outline_ready",
        )
        db.add(novel)
        await db.commit()
        await db.refresh(novel)

        yield _sse("outline", {**plan, "novel_id": novel.id})
        yield _sse("status", f"大纲已生成：《{title}》，共 {len(chapters_plan)} 章 — 请确认或编辑后开始创作")
        yield _sse("done", "")

    except Exception as e:
        logger.exception("Plan pipeline error: %s", e)
        yield _sse("error", f"规划管线异常：{e}")
    finally:
        await unload_model()
        set_llm_provider(None)
        logger.info("Plan pipeline finished")


@router.post("/plan")
async def plan_novel(
    req: NovelRequest,
    db: AsyncSession = Depends(get_db_session),
) -> EventSourceResponse:
    return EventSourceResponse(
        _plan_pipeline(req, db),
        media_type="text/event-stream",
    )


# ── Shared chapter writing logic ──────────────────────────────────

async def _write_chapters(
    novel: Novel,
    outline: OutlineResult,
    chapters_plan: list[dict],
    start_from: int,
    previous_summaries: list[str],
    recent_full_texts: list[str],
    db: AsyncSession,
) -> AsyncGenerator[dict, None]:
    """Core chapter-writing loop, used by both generate and resume."""
    main_characters_text = format_characters_for_prompt(
        [c.model_dump() for c in outline.main_characters]
    )

    for ch in chapters_plan:
        ch_num = ch["chapter_number"]
        if ch_num < start_from:
            continue

        ch_title = ch["title"]
        ch_brief = ch["brief"]

        yield _sse("status", f"正在撰写第 {ch_num} 章「{ch_title}」…")

        yield _sse("thinking", f"[GraphRAG] 查询 Neo4j 人物图谱…")
        char_ctx = await get_character_context(novel.id, ch_brief)
        if char_ctx:
            yield _sse("thinking", f"[GraphRAG] 获取到 {char_ctx.count('- ')} 条人物/关系信息")
        else:
            yield _sse("thinking", "[GraphRAG] 图谱暂无数据")

        memory_parts = []
        if previous_summaries:
            memory_parts.append(f"前文摘要 {len(previous_summaries)} 章")
        if recent_full_texts:
            memory_parts.append(f"近期全文 {len(recent_full_texts)} 章")
        if memory_parts:
            yield _sse("thinking", f"[记忆层] {' + '.join(memory_parts)}")

        chapter_text = ""
        async for chunk in write_chapter_stream(
            novel_title=outline.title,
            outline=outline.outline,
            chapter_title=ch_title,
            chapter_brief=ch_brief,
            chapter_number=ch_num,
            total_chapters=len(chapters_plan),
            previous_summaries=list(previous_summaries),
            character_context=char_ctx,
            recent_full_texts=recent_full_texts,
            world_building=outline.world_building,
            main_characters_text=main_characters_text,
            character_relationships=outline.character_relationships,
            writing_style=outline.writing_style,
        ):
            chapter_text += chunk
            yield _sse("text", chunk)

        row = await db.execute(
            select(Chapter).where(
                Chapter.novel_id == novel.id,
                Chapter.chapter_number == ch_num,
            )
        )
        all_matches = row.scalars().all()
        if not all_matches:
            chapter_row = Chapter(
                novel_id=novel.id,
                chapter_number=ch_num,
                title=ch_title,
                content=chapter_text,
                summary="",
                status="completed",
            )
            db.add(chapter_row)
        else:
            chapter_row = all_matches[0]
            chapter_row.content = chapter_text
            chapter_row.status = "completed"
            for dup in all_matches[1:]:
                await db.delete(dup)
        await db.commit()

        yield _sse("status", f"第 {ch_num} 章撰写完成，正在生成摘要…")
        summary = await summarize_chapter(chapter_text)
        chapter_row.summary = summary
        previous_summaries.append(summary)
        await db.commit()
        yield _sse("thinking", f"[摘要] 第 {ch_num} 章：{summary[:80]}…")

        recent_full_texts.append(chapter_text)
        if len(recent_full_texts) > RECENT_FULL_TEXT_CHAPTERS:
            recent_full_texts.pop(0)

        yield _sse("status", f"正在提取第 {ch_num} 章人物关系…")
        yield _sse("thinking", f"[Extractor] 分析第 {ch_num} 章文本…")

        try:
            graph_update = await extract_graph(chapter_text, ch_num)
            if graph_update.nodes or graph_update.edges:
                yield _sse("thinking",
                    f"[Extractor] {len(graph_update.nodes)} 人物、{len(graph_update.edges)} 关系 → Neo4j")
                await merge_graph(novel.id, graph_update, ch_num)
                full_graph = await query_full_graph(novel.id)
                yield _sse("graph", full_graph.model_dump())
            else:
                yield _sse("thinking", f"[Extractor] 第 {ch_num} 章无新人物/关系")
        except Exception as e:
            logger.warning("Graph extraction failed for chapter %d: %s", ch_num, e)
            yield _sse("thinking", f"[Extractor] 第 {ch_num} 章异常：{e}")

    novel.status = "completed"
    await db.commit()

    final_graph = await query_full_graph(novel.id)
    if final_graph.nodes:
        yield _sse("thinking",
            f"[完成] 全书 {len(final_graph.nodes)} 人物、{len(final_graph.edges)} 关系")

    yield _sse("status", f"《{outline.title}》全部 {len(chapters_plan)} 章撰写完成！")
    yield _sse("done", "")


# ── POST /api/generate — write from confirmed outline ────────────

async def _write_pipeline(
    novel_id: int, outline: OutlineResult, provider: str, db: AsyncSession
) -> AsyncGenerator[dict, None]:
    try:
        set_llm_provider(provider)

        result = await db.execute(select(Novel).where(Novel.id == novel_id))
        novel = result.scalar_one_or_none()
        if not novel:
            yield _sse("error", f"小说 #{novel_id} 不存在")
            return

        outline_dict = outline.model_dump()
        outline_json = json.dumps(outline_dict, ensure_ascii=False)

        novel.title = outline.title
        novel.outline = outline_json
        novel.status = "generating"
        await db.commit()

        # Clear leftover chapters
        existing = await db.execute(
            select(Chapter).where(Chapter.novel_id == novel.id)
        )
        for ch in existing.scalars().all():
            await db.delete(ch)
        await db.commit()

        chapters_plan = [c.model_dump() for c in outline.chapters]

        for ch in chapters_plan:
            db.add(Chapter(
                novel_id=novel.id,
                chapter_number=ch["chapter_number"],
                title=ch["title"],
                summary="",
                content="",
                status="pending",
            ))
        await db.commit()

        yield _sse("outline", {
            "title": outline.title,
            "outline": outline.outline,
            "chapters": chapters_plan,
        })
        provider_label = "本地 Ollama" if provider == "ollama" else "在线 Qwen API"
        yield _sse("status", f"开始撰写《{outline.title}》（{provider_label}），共 {len(chapters_plan)} 章")

        async for event in _write_chapters(
            novel, outline, chapters_plan,
            start_from=1,
            previous_summaries=[],
            recent_full_texts=[],
            db=db,
        ):
            yield event

    except Exception as e:
        logger.exception("Write pipeline error: %s", e)
        yield _sse("error", f"写作管线异常：{e}")
    finally:
        await unload_model()
        set_llm_provider(None)
        logger.info("Write pipeline finished")


@router.post("/generate")
async def generate_novel(
    req: GenerateFromOutlineRequest,
    db: AsyncSession = Depends(get_db_session),
) -> EventSourceResponse:
    return EventSourceResponse(
        _write_pipeline(req.novel_id, req.outline, req.provider, db),
        media_type="text/event-stream",
    )


# ── POST /api/resume — continue from where it left off ───────────

async def _resume_pipeline(
    novel_id: int, provider: str, db: AsyncSession
) -> AsyncGenerator[dict, None]:
    try:
        set_llm_provider(provider)

        result = await db.execute(
            select(Novel).where(Novel.id == novel_id).options(selectinload(Novel.chapters))
        )
        novel = result.scalar_one_or_none()
        if not novel:
            yield _sse("error", f"小说 #{novel_id} 不存在")
            return

        # Parse stored outline JSON
        try:
            outline_dict = json.loads(novel.outline)
            outline = OutlineResult(**outline_dict)
        except (json.JSONDecodeError, TypeError, Exception) as e:
            logger.error("Failed to parse stored outline for novel %d: %s", novel_id, e)
            yield _sse("error", f"无法解析存储的大纲数据（{type(e).__name__}），请重新生成")
            return
        chapters_plan = [c.model_dump() for c in outline.chapters]

        # Find completed chapters and build memory
        completed_chapters = sorted(
            [ch for ch in novel.chapters if ch.status == "completed" and ch.content],
            key=lambda c: c.chapter_number,
        )

        completed_nums = {ch.chapter_number for ch in completed_chapters}
        start_from = 1
        for ch in chapters_plan:
            if ch["chapter_number"] in completed_nums:
                start_from = ch["chapter_number"] + 1
            else:
                break

        if start_from > len(chapters_plan):
            novel.status = "completed"
            await db.commit()
            yield _sse("status", f"《{outline.title}》所有章节已完成")
            yield _sse("done", "")
            return

        # Rebuild memory from completed chapters
        previous_summaries = [ch.summary for ch in completed_chapters if ch.summary]
        recent_full_texts = [
            ch.content for ch in completed_chapters[-RECENT_FULL_TEXT_CHAPTERS:]
        ]

        # Deduplicate and ensure pending chapter records exist
        all_chapters_result = await db.execute(
            select(Chapter).where(Chapter.novel_id == novel.id)
        )
        all_existing = all_chapters_result.scalars().all()
        by_num: dict[int, list[Chapter]] = {}
        for ch_row in all_existing:
            by_num.setdefault(ch_row.chapter_number, []).append(ch_row)

        for num, rows in by_num.items():
            if len(rows) > 1:
                keep = next((r for r in rows if r.status == "completed"), rows[0])
                for r in rows:
                    if r is not keep:
                        await db.delete(r)

        existing_nums = set(by_num.keys())
        for ch in chapters_plan:
            if ch["chapter_number"] not in existing_nums:
                db.add(Chapter(
                    novel_id=novel.id,
                    chapter_number=ch["chapter_number"],
                    title=ch["title"],
                    summary="",
                    content="",
                    status="pending",
                ))
        await db.commit()

        novel.status = "generating"
        await db.commit()

        completed_count = len(completed_chapters)
        total_count = len(chapters_plan)
        provider_label = "本地 Ollama" if provider == "ollama" else "在线 Qwen API"

        yield _sse("outline", {
            "title": outline.title,
            "outline": outline.outline,
            "chapters": chapters_plan,
            "novel_id": novel.id,
        })
        yield _sse("thinking",
            f"[续写] 从第 {start_from} 章继续（已完成 {completed_count}/{total_count} 章），"
            f"已恢复 {len(previous_summaries)} 条摘要 + {len(recent_full_texts)} 段近期全文")
        yield _sse("status",
            f"续写《{outline.title}》（{provider_label}），从第 {start_from} 章开始，"
            f"共 {total_count - completed_count} 章待写")

        # Send completed chapters as text so frontend can display them
        for ch in completed_chapters:
            yield _sse("thinking", f"[已完成] 第 {ch.chapter_number} 章「{ch.title}」")

        # Emit graph if available
        full_graph = await query_full_graph(novel.id)
        if full_graph.nodes:
            yield _sse("graph", full_graph.model_dump())

        async for event in _write_chapters(
            novel, outline, chapters_plan,
            start_from=start_from,
            previous_summaries=previous_summaries,
            recent_full_texts=recent_full_texts,
            db=db,
        ):
            yield event

    except Exception as e:
        logger.exception("Resume pipeline error: %s", e)
        yield _sse("error", f"续写管线异常：{e}")
    finally:
        await unload_model()
        set_llm_provider(None)
        logger.info("Resume pipeline finished")


@router.post("/resume")
async def resume_novel(
    req: ResumeRequest,
    db: AsyncSession = Depends(get_db_session),
) -> EventSourceResponse:
    return EventSourceResponse(
        _resume_pipeline(req.novel_id, req.provider, db),
        media_type="text/event-stream",
    )
