"""pytest 配置 —— 测试夹具"""

import os
import tempfile
from pathlib import Path

import pytest

# 强制使用临时数据库，避免污染开发数据
os.environ["DATABASE_URL"] = "sqlite:///temp_test_tutorai.db"


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试前后清理数据库"""
    db_path = Path("temp_test_tutorai.db")
    if db_path.exists():
        db_path.unlink()
    yield
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def sample_text():
    return (
        "人工智能（Artificial Intelligence，简称 AI）是计算机科学的一个分支。"
        "它致力于开发能够模拟人类智能行为的系统。"
        "机器学习是 AI 的核心技术之一，通过数据训练模型来完成任务。"
        "深度学习使用多层神经网络，在图像识别、自然语言处理等领域取得了突破性进展。"
    )
