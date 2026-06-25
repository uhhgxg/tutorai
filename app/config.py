"""应用配置管理 —— 从环境变量 /.env 文件加载（pydantic-settings）"""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # JWT
    jwt_secret_key: str = "change-me-to-a-random-secret-key"

    # Embedding
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # CORS
    cors_origins: list[str] = ["*"]

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Database
    database_url: str = "sqlite:///data/tutorai.db"

    # OCR (Tesseract)
    tessdata_prefix: str = (
        "/usr/share/tesseract-ocr/5/tessdata"
        if os.name != "nt"
        else r"D:\tesseract\tessdata"
    )

    @property
    def db_path(self) -> str:
        return self.database_url.replace("sqlite:///", "")


settings = Settings()
