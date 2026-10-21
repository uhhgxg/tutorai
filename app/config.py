"""配置管理 —— pydantic-settings 从 .env 读取，支持环境隔离

使用方式：
  APP_ENV=dev    → 读取 .env（默认）
  APP_ENV=test   → 读取 .env + .env.test（test 覆盖 dev）
  APP_ENV=prod   → 读取 .env + .env.prod（prod 覆盖 dev）

安全说明：
- JWT_SECRET_KEY：生产环境必须设置强密钥，未设置时自动生成随机密钥并输出警告
- CORS_ORIGINS：生产环境禁止使用通配符 "*"，默认仅允许 localhost:3000
"""

import logging
import os
from pathlib import Path
from secrets import token_hex

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

APP_ENV = os.getenv("APP_ENV", "dev")

_env_files = [".env"]
if APP_ENV != "dev":
    specific = f".env.{APP_ENV}"
    if Path(specific).exists():
        _env_files.append(specific)
        logger.info("加载环境配置: %s (APP_ENV=%s)", specific, APP_ENV)


class Settings(BaseSettings):
    # --- LLM ---
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # --- App ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # --- Database ---
    database_url: str = "sqlite:///data/tutorai.db"

    # --- JWT（生产环境必须在 .env 中设置强密钥）---
    jwt_secret_key: str = ""

    # --- OCR (Tesseract) ---
    tessdata_prefix: str = "/usr/share/tesseract-ocr/5/tessdata"

    # --- CORS ——生产环境禁止使用通配符 "*"---
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- 上传文件大小上限（字节），默认 50MB ---
    max_upload_size: int = 50 * 1024 * 1024

    # --- Chunking ---
    chunk_size: int = 500
    chunk_overlap: int = 50

    # --- LLM Context ---
    max_context_chars: int = 3000
    max_history_chars: int = 12000
    max_memory_items: int = 10
    max_tool_result_chars: int = 3000
    max_agent_iterations: int = 4

    # --- Retrieval ---
    retrieval_candidate_multiplier: int = 2
    retrieval_score_threshold: float = 0.0
    preload_retriever: bool = False

    @field_validator("jwt_secret_key")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if not v:
            logging.warning(
                "⚠️  未设置 JWT_SECRET_KEY，已自动生成随机密钥（仅限开发环境）。"
                "生产环境必须在 .env 中设置固定强密钥，否则所有已签发 token 会在重启后失效。"
            )
            return token_hex(32)
        if len(v) < 16:
            logging.warning("⚠️  JWT_SECRET_KEY 长度不足 16 字符，建议至少 32 字符随机字符串。")
        return v

    @field_validator("cors_origins")
    @classmethod
    def _validate_cors(cls, v: list[str]) -> list[str]:
        if "*" in v:
            logging.warning(
                "⚠️  CORS_ORIGINS 包含通配符 '*'，任何网站均可跨域访问此 API。"
                "生产环境请在 .env 中设置具体的前端域名。"
            )
        return v

    @property
    def db_path(self) -> str:
        return self.database_url.replace("sqlite:///", "")

    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
