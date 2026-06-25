"""数据库操作测试"""

from app.database import (
    get_db, create_conversation, list_conversations,
    get_conversation, delete_conversation, add_message, get_messages,
    save_document, list_documents, get_document_chunks, delete_document,
)

_TEST_USER = "testuser"


def setup_module():
    from datetime import datetime, timezone
    from app.auth import hash_password
    conn = get_db()
    conn.executescript("DELETE FROM users; DELETE FROM documents; DELETE FROM conversations; DELETE FROM messages;")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (_TEST_USER, "dbuser", hash_password("test1234"), now),
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

        assert get_conversation(conn, cid) is not None
        delete_conversation(conn, cid)
        assert get_conversation(conn, cid) is None
        conn.close()


class TestMessages:
    def test_add_and_get(self):
        conn = get_db()
        conv = create_conversation(conn, _TEST_USER, "有消息的对话")
        add_message(conn, conv["id"], "user", "你好")
        add_message(conn, conv["id"], "assistant", "你好！有什么可以帮助你的？")

        msgs = get_messages(conn, conv["id"])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
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
