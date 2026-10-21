"""数据库操作测试"""

from datetime import UTC

from app.db.conversation_repo import (
    add_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_messages,
    list_conversations,
)
from app.db.document_repo import (
    delete_document,
    get_document_chunks,
    list_documents,
    save_document,
)
from app.db.engine import get_db_connection as get_db

_TEST_USER = "testuser"
_OTHER_USER = "otheruser"


def setup_module():
    from datetime import datetime

    from app.auth import hash_password
    conn = get_db()
    conn.executescript("DELETE FROM users; DELETE FROM documents; DELETE FROM conversations; DELETE FROM messages;")
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (_TEST_USER, "dbuser", hash_password("test1234"), now),
    )
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (_OTHER_USER, "otheruser", hash_password("test1234"), now),
    )
    conn.commit()
    conn.close()


class TestConversations:
    def test_create_and_list(self):
        conn = get_db()
        conv = create_conversation(conn, _TEST_USER, "测试对话")
        assert "id" in conv
        assert conv["title"] == "测试对话"

        convs = list_conversations(conn, _TEST_USER)
        assert len(convs) == 1
        conn.close()

    def test_get_and_delete(self):
        conn = get_db()
        conv = create_conversation(conn, _TEST_USER, "要删除的对话")
        cid = conv["id"]

        assert get_conversation(conn, cid, _TEST_USER) is not None
        delete_conversation(conn, cid, _TEST_USER)
        assert get_conversation(conn, cid, _TEST_USER) is None
        conn.close()


class TestMessages:
    def test_add_and_get(self):
        conn = get_db()
        conv = create_conversation(conn, _TEST_USER, "有消息的对话")
        add_message(conn, conv["id"], _TEST_USER, "user", "你好")
        add_message(conn, conv["id"], _TEST_USER, "assistant", "你好！有什么可以帮助你的？")

        msgs = get_messages(conn, conv["id"], _TEST_USER)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        conn.close()


class TestIDORProtection:
    """验证 IDOR 防护 — 用户 A 无法访问/操作用户 B 的对话"""

    def test_cannot_get_other_users_conversation(self):
        """用户 B 不能查看用户 A 的对话"""
        conn = get_db()
        conv = create_conversation(conn, _TEST_USER, "用户A的对话")
        conn.close()

        conn = get_db()
        assert get_conversation(conn, conv["id"], _OTHER_USER) is None
        conn.close()

    def test_cannot_delete_other_users_conversation(self):
        """用户 B 不能删除用户 A 的对话"""
        conn = get_db()
        conv = create_conversation(conn, _TEST_USER, "用户A的对话")
        conn.close()

        conn = get_db()
        assert delete_conversation(conn, conv["id"], _OTHER_USER) is False
        conn.close()

        # 确认对话仍然存在
        conn = get_db()
        assert get_conversation(conn, conv["id"], _TEST_USER) is not None
        conn.close()

    def test_cannot_add_message_to_other_users_conversation(self):
        """用户 B 不能向用户 A 的对话发消息"""
        conn = get_db()
        conv = create_conversation(conn, _TEST_USER, "用户A的对话")
        conn.close()

        conn = get_db()
        result = add_message(conn, conv["id"], _OTHER_USER, "user", "恶意消息")
        assert result is None
        conn.close()

        # 确认对话中没有消息
        conn = get_db()
        msgs = get_messages(conn, conv["id"], _TEST_USER)
        assert len(msgs) == 0
        conn.close()

    def test_cannot_get_messages_from_other_users_conversation(self):
        """用户 B 不能读取用户 A 对话的消息"""
        conn = get_db()
        conv = create_conversation(conn, _TEST_USER, "用户A的对话")
        add_message(conn, conv["id"], _TEST_USER, "user", "私密内容")
        conn.close()

        conn = get_db()
        msgs = get_messages(conn, conv["id"], _OTHER_USER)
        assert len(msgs) == 0
        conn.close()


class TestDocuments:
    def setup_method(self):
        conn = get_db()
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM document_chunks")
        conn.commit()
        conn.close()

    def test_save_and_list(self):
        conn = get_db()
        doc = save_document(conn, _TEST_USER, "test.txt", "测试内容", ["测试内容"])
        assert doc["filename"] == "test.txt"
        assert doc["chunk_count"] == 1

        docs = list_documents(conn, _TEST_USER)
        assert len(docs) == 1

        chunks = get_document_chunks(conn, _TEST_USER, doc["id"])
        assert len(chunks) == 1
        assert chunks[0] == "测试内容"
        conn.close()

    def test_delete(self):
        conn = get_db()
        doc = save_document(conn, _TEST_USER, "to_delete.txt", "内容", ["内容"])
        assert delete_document(conn, _TEST_USER, doc["id"]) is True
        assert delete_document(conn, _TEST_USER, "nonexistent") is False
        assert len(list_documents(conn, _TEST_USER)) == 0
        conn.close()
