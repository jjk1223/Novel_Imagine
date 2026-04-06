from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: Literal["ollama", "qwen"] = "ollama"

    ollama_base_url: str = "http://host.docker.internal:11434/v1"
    ollama_model: str = "qwen2.5:7b"

    qwen_api_key: str = "sk-xxx"
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"

    # Neo4j
    neo4j_uri: str = "bolt://host.docker.internal:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "your_password"

    # SQLite
    sqlite_url: str = "sqlite+aiosqlite:///./data/novel.db"

    @property
    def llm_base_url(self) -> str:
        return self.ollama_base_url if self.llm_provider == "ollama" else self.qwen_base_url

    @property
    def llm_api_key(self) -> str:
        return "ollama" if self.llm_provider == "ollama" else self.qwen_api_key

    @property
    def llm_model(self) -> str:
        return self.ollama_model if self.llm_provider == "ollama" else self.qwen_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
