"""pytest 配置 —— 测试夹具

### 注意事项
- TF-IDF 检索器无需 mock（纯 scikit-learn，进程内运行）
- 强制使用临时 SQLite 数据库，隔离开发数据
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════
# 数据库隔离
# ═══════════════════════════════════════════════════════════

_test_db_dir = tempfile.mkdtemp(prefix="tutorai_test_")
_test_db_path = os.path.join(_test_db_dir, "test_tutorai.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试前后清理数据库"""
    db_path = Path(_test_db_path)
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        p = db_path.parent / f"{db_path.name}{suffix}"
        if p.exists():
            p.unlink()
    yield
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        p = db_path.parent / f"{db_path.name}{suffix}"
        if p.exists():
            p.unlink()


@pytest.fixture(scope="session", autouse=True)
def _clean_test_db_dir():
    """会话结束时清理临时目录"""
    yield
    import shutil
    shutil.rmtree(_test_db_dir, ignore_errors=True)


@pytest.fixture
def sample_text():
    return (
        "人工智能（Artificial Intelligence，简称 AI）是计算机科学的一个分支。"
        "它致力于开发能够模拟人类智能行为的系统。"
        "机器学习是 AI 的核心技术之一，通过数据训练模型来完成任务。"
        "深度学习使用多层神经网络，在图像识别、自然语言处理等领域取得了突破性进展。"
    )
