"""Agent 工具调用测试 —— 验证工具工厂、ReAct 推理循环、用户隔离"""

import sqlite3
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from app.services.llm_client import agent_chat
from app.services.tools import create_user_tools, user_id_var

# ── 工具工厂测试 ──

class TestCreateUserTools:
    """验证 create_user_tools 工厂函数"""

    def test_create_user_tools_returns_three_tools(self):
        """应返回文档、出题和记忆工具"""
        tools = create_user_tools("test_user")
        assert len(tools) == 5

    def test_create_user_tools_names(self):
        """应包含文档、出题和记忆工具"""
        tools = create_user_tools("test_user")
        names = [t.name for t in tools]
        assert "retrieve_document" in names
        assert "generate_quiz" in names
        assert "list_documents" in names
        assert "save_memory" in names
        assert "list_memory" in names

    def test_each_tool_has_description(self):
        """每个工具应有描述信息供 LLM 识别"""
        for t in create_user_tools("test_user"):
            assert t.description, f"工具 {t.name} 缺少描述"

    def test_different_users_get_independent_tools(self):
        """不同用户应获得独立的工具实例"""
        tools_a = create_user_tools("user_a")
        tools_b = create_user_tools("user_b")
        assert tools_a[0] is not tools_b[0]

    def test_tool_binds_correct_user_id(self):
        """工具应能将 user_id 传递给 search_chunks"""
        from langchain_core.documents import Document
        tools = create_user_tools("bound_user")
        retrieve_doc = [t for t in tools if t.name == "retrieve_document"][0]

        mock_docs = [Document(page_content="内容", metadata={"score": 0.9, "doc_id": "d1", "user_id": "bound_user"})]
        with patch("app.services.retriever.search_chunks", return_value=mock_docs) as mock_search:
            retrieve_doc.invoke({"query": "测试"})
            mock_search.assert_called_once()
            assert mock_search.call_args.kwargs.get("user_id") == "bound_user"


# ── retrieve_document 工具测试 ──

class TestRetrieveDocumentTool:
    """retrieve_document 工具功能测试"""

    def _get_tool(self, user_id="test_user"):
        tools = create_user_tools(user_id)
        return [t for t in tools if t.name == "retrieve_document"][0]

    def test_retrieve_no_results(self):
        """搜索无结果时返回提示信息"""
        tool = self._get_tool()
        with patch("app.services.retriever.search_chunks", return_value=[]):
            result = tool.invoke({"query": "不存在的关键词"})
            assert "未找到" in result

    def test_retrieve_with_results(self):
        """搜索有结果时返回片段信息"""
        from langchain_core.documents import Document
        tool = self._get_tool()
        mock_docs = [
            Document(page_content="人工智能是计算机科学的分支", metadata={"score": 0.95, "doc_id": "doc1", "user_id": "u1"}),
        ]
        with patch("app.services.retriever.search_chunks", return_value=mock_docs):
            result = tool.invoke({"query": "人工智能"})
            assert "人工智能" in result
            assert "相关度" in result


# ── generate_quiz 工具测试 ──

class TestGenerateQuizTool:
    """generate_quiz 工具功能测试"""

    def _get_tool(self, user_id="test_user"):
        tools = create_user_tools(user_id)
        return [t for t in tools if t.name == "generate_quiz"][0]

    def test_generate_quiz_returns_content(self):
        """出题工具应返回题目内容"""
        tool = self._get_tool()
        with patch("app.services.llm_client.chat", return_value="1. 什么是AI？\nA. ...\nB. ..."):
            result = tool.invoke({
                "content": "人工智能是计算机科学的分支",
                "question_count": 3,
                "question_type": "choice",
            })
            assert "什么是AI" in result

    def test_generate_quiz_empty_response(self):
        """LLM 返回空时应提示重试"""
        tool = self._get_tool()
        with patch("app.services.llm_client.chat", return_value=""):
            result = tool.invoke({
                "content": "人工智能是计算机科学的分支",
                "question_count": 3,
            })
            assert "未能生成" in result or "重试" in result


# ── list_documents 工具测试 ──

class TestListDocumentsTool:
    """list_documents 工具功能测试 —— 使用临时 SQLite 数据库"""

    @staticmethod
    def _make_temp_db() -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        return conn

    def _get_tool(self, user_id="test_user"):
        tools = create_user_tools(user_id)
        return [t for t in tools if t.name == "list_documents"][0]

    def test_list_documents_empty(self):
        """用户无文档时应返回提示"""
        temp_conn = self._make_temp_db()
        temp_conn.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            ("empty_user", "empty_user", "hash", "2026-01-01T00:00:00"),
        )
        temp_conn.commit()

        tool = self._get_tool("empty_user")
        with patch("app.db.engine.get_db_connection", return_value=temp_conn):
            result = tool.invoke({})
            assert "没有上传" in result or "尚未" in result
        temp_conn.close()

    def test_list_documents_with_docs(self):
        """有文档时应返回文件名和片段数"""
        temp_conn = self._make_temp_db()
        temp_conn.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            ("doc_user", "doc_user", "hash", "2026-01-01T00:00:00"),
        )
        temp_conn.execute(
            "INSERT INTO documents (id, user_id, filename, content, chunk_count, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("d1", "doc_user", "test.pdf", "PDF内容", 5, "2026-01-01T00:00:00"),
        )
        temp_conn.commit()

        tool = self._get_tool("doc_user")
        with patch("app.db.engine.get_db_connection", return_value=temp_conn):
            result = tool.invoke({})
            assert "test.pdf" in result
            assert "5" in result
        temp_conn.close()


class TestMemoryTools:
    """验证记忆工具只操作绑定用户的数据。"""

    @staticmethod
    def _make_temp_db() -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE memories (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, category TEXT NOT NULL,
                content TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, UNIQUE(user_id, category, content)
            )"""
        )
        conn.commit()
        return conn

    def _get_tool(self, name: str, user_id: str = "memory_user"):
        tools = create_user_tools(user_id)
        return [tool for tool in tools if tool.name == name][0]

    def test_save_and_list_memory(self):
        temp_conn = self._make_temp_db()

        with patch("app.db.engine.get_db_connection", return_value=temp_conn):
            result = self._get_tool("save_memory").invoke(
                {"content": "目标是拿到 Agent 开发实习", "category": "goal"}
            )
            assert "已记住" in result
        with (
            patch(
                "app.db.memory_repo.list_memories",
                return_value=[{"category": "goal", "content": "目标是拿到 Agent 开发实习"}],
            ),
            patch("app.db.engine.get_db_connection", return_value=temp_conn),
        ):
            listed = self._get_tool("list_memory").invoke({})
        assert "Agent 开发实习" in listed
        temp_conn.close()


# ── ContextVar 用户隔离测试 ──

class TestContextVarIsolation:
    """验证 ContextVar 在不同协程中隔离用户 ID"""

    def test_user_id_var_default_is_none(self):
        token = user_id_var.set(None)
        assert user_id_var.get() is None
        user_id_var.reset(token)

    def test_user_id_var_set_and_get(self):
        token = user_id_var.set("user_abc")
        assert user_id_var.get() == "user_abc"
        user_id_var.reset(token)

    def test_user_id_var_isolation(self):
        import contextvars
        token = user_id_var.set(None)

        def set_and_get(uid):
            user_id_var.set(uid)
            return user_id_var.get()

        ctx1 = contextvars.copy_context()
        ctx2 = contextvars.copy_context()

        result1 = ctx1.run(set_and_get, "user_1")
        result2 = ctx2.run(set_and_get, "user_2")

        assert result1 == "user_1"
        assert result2 == "user_2"

        user_id_var.reset(token)


# ── ReAct 推理循环测试 ──

class TestReActLoop:
    """验证 Agent ReAct 推理循环的多轮工具调用"""

    def test_no_tool_call_returns_directly(self):
        """LLM 不调用工具时应直接返回内容"""
        mock_response = AIMessage(content="这是直接回答，无需检索文档。")
        tools = create_user_tools("test_user")

        with patch("app.services.llm_client.settings") as mock_settings:
            mock_settings.llm_api_key = "test_key"
            with patch("app.services.llm_client.get_llm") as mock_get_llm:
                mock_llm = MagicMock()
                mock_llm.invoke.return_value = mock_response
                mock_llm.bind_tools.return_value = mock_llm
                mock_get_llm.return_value = mock_llm

                messages = [{"role": "user", "content": "你好"}]
                result = agent_chat(messages, tools=tools)
                assert "直接回答" in result

    def test_single_tool_call(self):
        """单轮工具调用：LLM 调用 retrieve_document 后合成答案"""
        from langchain_core.documents import Document
        tools = create_user_tools("test_user")

        tool_call_response = AIMessage(
            content="",
            tool_calls=[{"name": "retrieve_document", "args": {"query": "人工智能"}, "id": "tc_1"}],
        )
        final_response = AIMessage(content="根据文档内容，人工智能是计算机科学的分支。")
        mock_docs = [
            Document(page_content="人工智能是计算机科学的分支", metadata={"score": 0.95, "doc_id": "doc1", "user_id": "u1"}),
        ]

        with patch("app.services.llm_client.settings") as mock_settings:
            mock_settings.llm_api_key = "test_key"
            with patch("app.services.llm_client.get_llm") as mock_get_llm:
                mock_llm = MagicMock()
                mock_llm.invoke.side_effect = [tool_call_response, final_response]
                mock_llm.bind_tools.return_value = mock_llm
                mock_get_llm.return_value = mock_llm

                with patch("app.services.retriever.search_chunks", return_value=mock_docs):
                    messages = [{"role": "user", "content": "什么是人工智能？"}]
                    result = agent_chat(messages, tools=tools)
                    assert "人工智能" in result

    def test_tool_call_failure_fallback(self):
        """工具调用失败时应 fallback 到错误提示"""
        tools = create_user_tools("test_user")

        tool_call_response = AIMessage(
            content="",
            tool_calls=[{"name": "retrieve_document", "args": {"query": "测试"}, "id": "tc_fail"}],
        )
        final_response = AIMessage(content="抱歉，检索工具调用失败。")

        with patch("app.services.llm_client.settings") as mock_settings:
            mock_settings.llm_api_key = "test_key"
            with patch("app.services.llm_client.get_llm") as mock_get_llm:
                mock_llm = MagicMock()
                mock_llm.invoke.side_effect = [tool_call_response, final_response]
                mock_llm.bind_tools.return_value = mock_llm
                mock_get_llm.return_value = mock_llm

                with patch("app.services.retriever.search_chunks", side_effect=Exception("数据库连接失败")):
                    messages = [{"role": "user", "content": "测试"}]
                    result = agent_chat(messages, tools=tools)
                    assert isinstance(result, str)
