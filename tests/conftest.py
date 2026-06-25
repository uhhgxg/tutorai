"""pytest 配置 —— 测试夹具

- 使用临时 SQLite 数据库隔离开发数据
- 每个测试类自行管理数据清理
"""

import os
import tempfile

import pytest

_test_db_dir = tempfile.mkdtemp(prefix="tutorai_test_")
_test_db_path = os.path.join(_test_db_dir, "test_tutorai.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
# 强制使用 DELETE journal 模式，避免 WAL 文件锁定问题
os.environ["DB_JOURNAL_MODE"] = "DELETE"


@pytest.fixture(scope="session", autouse=True)
def _clean_test_db_dir():
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
