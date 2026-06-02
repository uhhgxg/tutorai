"""数据库操作测试"""

import sqlite3
from app.database import (
    get_db, create_conversation, list_conversations,
    get_conversation, delete_conversation, add_message, get_messages,
    save_document, list_documents, get_document_chunks, delete_document,
)


class TestConversations:
    def test_create_and_list(self):
        conn = get_db()
        conv = create_conversation(conn, "测试对话")
        assert "id" in conv
        assert conv["title"] == "测试对话"

        convs = list_conversations(conn)
        assert len(convs) == 1
        conn.close()

    def test_get_and_delete(self):
        conn = get_db()
        conv = create_conversation(conn, "要删除的对话")
        cid = conv["id"]

        assert get_conversation(conn, cid) is not None
        delete_conversation(conn, cid)
        assert get_conversation(conn, cid) is None
        conn.close()


class TestMessages:
    def test_add_and_get(self):
        conn = get_db()
        conv = create_conversation(conn, "有消息的对话")
        add_message(conn, conv["id"], "user", "你好")
        add_message(conn, conv["id"], "assistant", "你好！有什么可以帮助你的？")

        msgs = get_messages(conn, conv["id"])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        conn.close()


class TestDocuments:
    def test_save_and_list(self):
        conn = get_db()
        doc = save_document(conn, "test.txt", "测试内容", ["测试内容"])
        assert doc["filename"] == "test.txt"
        assert doc["chunk_count"] == 1

        docs = list_documents(conn)
        assert len(docs) == 1

        chunks = get_document_chunks(conn, doc["id"])
        assert len(chunks) == 1
        assert chunks[0] == "测试内容"
        conn.close()

    def test_delete(self):
        conn = get_db()
        doc = save_document(conn, "to_delete.txt", "内容", ["内容"])
        assert delete_document(conn, doc["id"]) is True
        assert delete_document(conn, "nonexistent") is False
        assert len(list_documents(conn)) == 0
        conn.close()
