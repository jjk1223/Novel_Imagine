import logging
from typing import AsyncGenerator

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession

from app.config import get_settings

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None


async def init_neo4j() -> None:
    global _driver
    settings = get_settings()
    _driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        await _driver.verify_connectivity()
        logger.info("Neo4j connection verified successfully")
    except Exception as e:
        logger.warning("Neo4j connectivity check failed: %s — graph features will be unavailable", e)


async def close_neo4j() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")


def get_driver() -> AsyncDriver | None:
    return _driver


async def get_neo4j_session() -> AsyncGenerator[AsyncSession, None]:
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialised — call init_neo4j() first")
    async with _driver.session() as session:
        yield session
