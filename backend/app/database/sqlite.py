import datetime
from typing import AsyncGenerator

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class Novel(Base):
    __tablename__ = "novels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    premise: Mapped[str] = mapped_column(Text, default="")
    outline: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="novel", cascade="all, delete-orphan", order_by="Chapter.chapter_number"
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    novel_id: Mapped[int] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"))
    chapter_number: Mapped[int] = mapped_column(default=0)
    title: Mapped[str] = mapped_column(String(256), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    novel: Mapped["Novel"] = relationship(back_populates="chapters")


engine = create_async_engine(get_settings().sqlite_url, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
