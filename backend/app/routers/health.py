import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.database.neo4j import get_driver
from app.database.sqlite import engine
from app.models.schemas import HealthResponse
from app.services.llm import check_connectivity as llm_check

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    # SQLite
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        sqlite_status = "ok"
    except Exception as e:
        sqlite_status = f"error: {e}"

    # Neo4j
    driver = get_driver()
    if driver is None:
        neo4j_status = "not initialised"
    else:
        try:
            await driver.verify_connectivity()
            neo4j_status = "ok"
        except Exception as e:
            neo4j_status = f"error: {e}"

    # LLM
    llm_ok = await llm_check()
    llm_status = "ok" if llm_ok else "unreachable"

    overall = "ok" if sqlite_status == "ok" else "degraded"
    return HealthResponse(status=overall, sqlite=sqlite_status, neo4j=neo4j_status, llm=llm_status)
