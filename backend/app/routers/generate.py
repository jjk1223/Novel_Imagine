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
    compile_tiered_memory,
    format_characters_for_prompt,
    summarize_chapter_structured,
    derive_plain_summary,
    write_chapter_stream,
)
from app.agents.reflector import reflect_chapter
from app.agents.reverse_outliner import run_reverse_outline
from app.config import get_settings
from app.database.sqlite import Chapter, Novel, get_db_session
from app.models.schemas import (
    GenerateFromOutlineRequest,
    NovelRequest,
    OutlineResult,
    ResumeRequest,
    StructuredSummary,
)
from app.services.graph import get_character_context, merge_graph, query_full_graph
from app.services.llm import set_llm_provider, unload_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generate"])

MAX_PLANNER_RETRIES = 3


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
    structured_summaries: list[StructuredSummary],
    chapter_numbers: list[int],
    recent_full_texts: list[str],
    db: AsyncSession,
) -> AsyncGenerator[dict, None]:
    """Core chapter-writing loop with structured summaries, tiered memory,
    reflect agent, and reverse-outline optimization."""
    settings = get_settings()
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

        # GraphRAG query
        yield _sse("thinking", f"[GraphRAG] 查询 Neo4j 故事图谱…")
        char_ctx = await get_character_context(novel.id, ch_brief)
        if char_ctx:
            yield _sse("thinking", f"[GraphRAG] 获取到 {char_ctx.count('- ')} 条实体/关系信息")
        else:
            yield _sse("thinking", "[GraphRAG] 图谱暂无数据")

        # Build tiered memory
        tiered_memory = compile_tiered_memory(structured_summaries, chapter_numbers)

        memory_parts = []
        if structured_summaries:
            memory_parts.append(f"结构化记忆 {len(structured_summaries)} 章")
        if recent_full_texts:
            memory_parts.append(f"近期全文 {len(recent_full_texts)} 章")
        if memory_parts:
            yield _sse("thinking", f"[记忆层] 核心设定 + {' + '.join(memory_parts)}")

        # Stream chapter text
        chapter_text = ""
        async for chunk in write_chapter_stream(
            novel_title=outline.title,
            outline=outline.outline,
            chapter_title=ch_title,
            chapter_brief=ch_brief,
            chapter_number=ch_num,
            total_chapters=len(chapters_plan),
            tiered_memory=tiered_memory,
            character_context=char_ctx,
            recent_full_texts=recent_full_texts,
            world_building=outline.world_building,
            main_characters_text=main_characters_text,
            character_relationships=outline.character_relationships,
            writing_style=outline.writing_style,
        ):
            chapter_text += chunk
            yield _sse("text", chunk)

        # Persist chapter to DB
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
                structured_summary="",
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

        # ── Structured summary ──────────────────────────────────
        yield _sse("status", f"第 {ch_num} 章撰写完成，正在生成结构化摘要…")
        structured = await summarize_chapter_structured(chapter_text, ch_num)
        chapter_row.structured_summary = json.dumps(
            structured.model_dump(), ensure_ascii=False
        )
        plain_summary = derive_plain_summary(structured, ch_num)
        chapter_row.summary = plain_summary
        structured_summaries.append(structured)
        chapter_numbers.append(ch_num)
        await db.commit()
        yield _sse("thinking", f"[摘要] 第 {ch_num} 章：{structured.plot_progress[:80]}…")

        # ── Reflect agent ───────────────────────────────────────
        if settings.reflect_enabled:
            yield _sse("status", f"正在审校第 {ch_num} 章…")
            yield _sse("thinking", f"[Reflect] 审校第 {ch_num} 章…")

            try:
                reflect_result = await reflect_chapter(
                    chapter_text=chapter_text,
                    chapter_number=ch_num,
                    chapter_brief=ch_brief,
                    world_building=outline.world_building,
                    main_characters_text=main_characters_text,
                    character_relationships=outline.character_relationships,
                    tiered_memory=tiered_memory,
                    outline=outline.outline,
                )

                yield _sse("reflect", {
                    "issues_found": reflect_result.issues_found,
                    "issues": reflect_result.issues,
                    "reasoning": reflect_result.reasoning,
                })

                if reflect_result.issues_found:
                    issues_text = "；".join(reflect_result.issues[:3])
                    yield _sse("thinking",
                        f"[Reflect] 发现 {len(reflect_result.issues)} 个问题：{issues_text}")

                    # Rewrite chapter if configured
                    if settings.reflect_max_retries > 0:
                        yield _sse("status", f"正在根据审校意见改写第 {ch_num} 章…")
                        yield _sse("thinking", f"[Reflect] 改写第 {ch_num} 章…")

                        feedback = "\n".join(
                            f"- {issue}" for issue in reflect_result.issues
                        )

                        rewritten_text = ""
                        async for chunk in write_chapter_stream(
                            novel_title=outline.title,
                            outline=outline.outline,
                            chapter_title=ch_title,
                            chapter_brief=ch_brief,
                            chapter_number=ch_num,
                            total_chapters=len(chapters_plan),
                            tiered_memory=tiered_memory,
                            character_context=char_ctx,
                            recent_full_texts=recent_full_texts,
                            world_building=outline.world_building,
                            main_characters_text=main_characters_text,
                            character_relationships=outline.character_relationships,
                            writing_style=outline.writing_style,
                            reflect_feedback=feedback,
                        ):
                            rewritten_text += chunk
                            yield _sse("text", chunk)

                        # Update DB with rewritten text
                        chapter_row.content = rewritten_text
                        chapter_text = rewritten_text
                        await db.commit()
                        yield _sse("thinking", f"[Reflect] 第 {ch_num} 章改写完成")
                else:
                    yield _sse("thinking", f"[Reflect] 第 {ch_num} 章审校通过")

            except Exception as e:
                logger.warning("Reflect agent failed for chapter %d: %s", ch_num, e)
                yield _sse("thinking", f"[Reflect] 第 {ch_num} 章审校异常：{e}")

        # ── Update recent full texts (Tier 3) ───────────────────
        recent_full_texts.append(chapter_text)
        if len(recent_full_texts) > settings.recent_full_text_chapters:
            recent_full_texts.pop(0)

        # ── Graph extraction ────────────────────────────────────
        yield _sse("status", f"正在提取第 {ch_num} 章故事实体…")
        yield _sse("thinking", f"[Extractor] 分析第 {ch_num} 章文本…")

        try:
            graph_update = await extract_graph(chapter_text, ch_num)
            if graph_update.nodes or graph_update.edges:
                yield _sse("thinking",
                    f"[Extractor] {len(graph_update.nodes)} 实体、{len(graph_update.edges)} 关系 → Neo4j")
                await merge_graph(novel.id, graph_update, ch_num)
                full_graph = await query_full_graph(novel.id)
                yield _sse("graph", full_graph.model_dump())
            else:
                yield _sse("thinking", f"[Extractor] 第 {ch_num} 章无新实体/关系")
        except Exception as e:
            logger.warning("Graph extraction failed for chapter %d: %s", ch_num, e)
            yield _sse("thinking", f"[Extractor] 第 {ch_num} 章异常：{e}")

        # ── Reverse outline optimization ────────────────────────
        if (settings.reverse_outline_enabled
                and ch_num > 0
                and ch_num % settings.reverse_outline_interval == 0
                and ch_num < len(chapters_plan)):

            yield _sse("status", "正在运行逆向大纲优化…")
            yield _sse("thinking", f"[ReverseOutline] 分析前 {ch_num} 章 vs 原始大纲…")

            try:
                written_summary = compile_tiered_memory(structured_summaries, chapter_numbers)
                remaining = [c for c in chapters_plan if c["chapter_number"] > ch_num]

                reverse_result = await run_reverse_outline(
                    written_chapters_text=written_summary,
                    original_outline=outline.outline,
                    original_chapters=remaining,
                    character_relationships=outline.character_relationships,
                    world_building=outline.world_building,
                    completed_count=ch_num,
                    total_count=len(chapters_plan),
                )

                yield _sse("reverse_outline", {
                    "analysis": reverse_result.analysis,
                    "updated_chapters_count": len(reverse_result.updated_chapters_remaining),
                })

                yield _sse("thinking",
                    f"[ReverseOutline] 偏差分析：{reverse_result.analysis[:100]}…\n"
                    f"已调整 {len(reverse_result.updated_chapters_remaining)} 个后续章节大纲")

                # Apply outline updates
                if reverse_result.outline_updates.get("character_relationships"):
                    outline.character_relationships = reverse_result.outline_updates["character_relationships"]
                if reverse_result.outline_updates.get("outline"):
                    outline.outline = reverse_result.outline_updates["outline"]

                # Update remaining chapters in chapters_plan
                if reverse_result.updated_chapters_remaining:
                    updated_by_num = {
                        ch.chapter_number: ch.model_dump()
                        for ch in reverse_result.updated_chapters_remaining
                    }
                    for i, c in enumerate(chapters_plan):
                        if c["chapter_number"] in updated_by_num:
                            chapters_plan[i] = updated_by_num[c["chapter_number"]]

                # Persist updated outline
                novel.outline = json.dumps(outline.model_dump(), ensure_ascii=False)
                await db.commit()

            except Exception as e:
                logger.warning("Reverse outline failed after chapter %d: %s", ch_num, e)
                yield _sse("thinking", f"[ReverseOutline] 异常：{e}")

    novel.status = "completed"
    await db.commit()

    final_graph = await query_full_graph(novel.id)
    if final_graph.nodes:
        yield _sse("thinking",
            f"[完成] 全书 {len(final_graph.nodes)} 实体、{len(final_graph.edges)} 关系")

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
            structured_summaries=[],
            chapter_numbers=[],
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
    settings = get_settings()
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

        # Rebuild structured summaries from completed chapters
        structured_summaries: list[StructuredSummary] = []
        chapter_numbers: list[int] = []
        for ch in completed_chapters:
            if ch.structured_summary:
                try:
                    ss = StructuredSummary(**json.loads(ch.structured_summary))
                    structured_summaries.append(ss)
                    chapter_numbers.append(ch.chapter_number)
                except (json.JSONDecodeError, TypeError):
                    # Fallback: create minimal structured summary from plain text
                    structured_summaries.append(StructuredSummary(plot_progress=ch.summary))
                    chapter_numbers.append(ch.chapter_number)
            elif ch.summary:
                structured_summaries.append(StructuredSummary(plot_progress=ch.summary))
                chapter_numbers.append(ch.chapter_number)

        recent_full_texts = [
            ch.content for ch in completed_chapters[-settings.recent_full_text_chapters:]
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
            f"已恢复 {len(structured_summaries)} 条结构化记忆 + {len(recent_full_texts)} 段近期全文")
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
            structured_summaries=structured_summaries,
            chapter_numbers=chapter_numbers,
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
