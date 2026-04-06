import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.neo4j import close_neo4j, init_neo4j
from app.database.sqlite import init_db
from app.routers import generate, health, novels

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting up — initialising databases …")
    await init_db()
    logger.info("SQLite tables ready")
    await init_neo4j()
    yield
    logger.info("Shutting down — closing connections …")
    await close_neo4j()


app = FastAPI(
    title="Novel Imagine API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(generate.router)
app.include_router(novels.router)
