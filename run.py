"""TutorAI — 启动入口

国内用户首次运行会从 HuggingFace 下载 bge-small-zh-v1.5 嵌入模型（约 400MB）。
如果下载缓慢，可设置镜像加速：
    export HF_ENDPOINT=https://hf-mirror.com
或在 .env 文件中添加：
    HF_ENDPOINT=https://hf-mirror.com
"""
import os
import uvicorn

# 国内 HuggingFace 镜像加速（优先读取环境变量，未设置则使用默认镜像）
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from app.main import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
