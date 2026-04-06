"""Novels CRUD — list, detail, and download endpoints."""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.sqlite import Chapter, Novel, get_db_session
from app.models.schemas import ChapterOut, NovelListItem, NovelOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels", tags=["novels"])


@router.get("", response_model=list[NovelListItem])
async def list_novels(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(
        select(
            Novel.id,
            Novel.title,
            Novel.premise,
            Novel.status,
            Novel.created_at,
            func.count(Chapter.id).label("chapter_count"),
        )
        .outerjoin(Chapter, Chapter.novel_id == Novel.id)
        .group_by(Novel.id)
        .order_by(Novel.created_at.desc())
    )
    rows = result.all()
    return [
        NovelListItem(
            id=r.id,
            title=r.title,
            premise=r.premise,
            status=r.status,
            created_at=r.created_at,
            chapter_count=r.chapter_count,
        )
        for r in rows
    ]


@router.get("/{novel_id}", response_model=NovelOut)
async def get_novel(novel_id: int, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(
        select(Novel)
        .where(Novel.id == novel_id)
        .options(selectinload(Novel.chapters))
    )
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    return NovelOut(
        id=novel.id,
        title=novel.title,
        premise=novel.premise,
        outline=novel.outline,
        status=novel.status,
        created_at=novel.created_at,
        chapters=[
            ChapterOut(
                id=ch.id,
                chapter_number=ch.chapter_number,
                title=ch.title,
                summary=ch.summary,
                content=ch.content,
                status=ch.status,
            )
            for ch in novel.chapters
        ],
    )


def _build_markdown(novel: Novel) -> str:
    lines = [f"# {novel.title}\n"]
    if novel.outline:
        lines.append(f"> {novel.outline}\n")
    lines.append("---\n")
    for ch in novel.chapters:
        if ch.content:
            lines.append(f"## 第{ch.chapter_number}章 {ch.title}\n")
            lines.append(ch.content)
            lines.append("\n")
    return "\n".join(lines)


def _build_plain(novel: Novel) -> str:
    lines = [novel.title, "=" * len(novel.title) * 2, ""]
    if novel.outline:
        lines.extend([novel.outline, ""])
    lines.append("-" * 40)
    lines.append("")
    for ch in novel.chapters:
        if ch.content:
            lines.append(f"第{ch.chapter_number}章 {ch.title}")
            lines.append("")
            lines.append(ch.content)
            lines.append("")
            lines.append("")
    return "\n".join(lines)


@router.get("/{novel_id}/download")
async def download_novel(
    novel_id: int,
    format: str = "md",
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Novel)
        .where(Novel.id == novel_id)
        .options(selectinload(Novel.chapters))
    )
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    safe_title = novel.title.replace("/", "_").replace("\\", "_") or "novel"

    def _cd_header(ext: str) -> str:
        ascii_fallback = f"novel_{novel_id}.{ext}"
        encoded = quote(f"{safe_title}.{ext}")
        return (
            f"attachment; filename=\"{ascii_fallback}\"; "
            f"filename*=UTF-8''{encoded}"
        )

    if format == "md":
        content = _build_markdown(novel)
        return PlainTextResponse(
            content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": _cd_header("md")},
        )

    content = _build_plain(novel)
    return PlainTextResponse(
        content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": _cd_header("txt")},
    )


@router.delete("/{novel_id}")
async def delete_novel(novel_id: int, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(Novel).where(Novel.id == novel_id))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    await db.delete(novel)
    await db.commit()
    return {"ok": True}
