"""聊天 API 测试"""
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db

client = TestClient(app)


def setup_module():
    """确保测试用数据库已就绪"""
    conn = get_db()
    conn.close()


class TestChatAPI:
    def test_list_conversations_empty(self):
        resp = client.get("/api/conversations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_conversation(self):
        resp = client.post("/api/conversations", params={"title": "测试对话"})
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["title"] == "测试对话"
        return data["id"]

    def test_create_conversation_default_title(self):
        resp = client.post("/api/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "新对话"

    def test_get_messages_empty(self):
        resp = client.post("/api/conversations", params={"title": "空对话"})
        conv_id = resp.json()["id"]

        resp = client.get(f"/api/conversations/{conv_id}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_messages_nonexistent(self):
        resp = client.get("/api/conversations/nonexistent/messages")
        assert resp.status_code == 404

    def test_delete_conversation(self):
        resp = client.post("/api/conversations", params={"title": "待删除"})
        conv_id = resp.json()["id"]

        resp = client.delete(f"/api/conversations/{conv_id}")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        resp = client.get("/api/conversations")
        assert all(c["id"] != conv_id for c in resp.json())

    def test_delete_nonexistent(self):
        resp = client.delete("/api/conversations/nonexistent")
        assert resp.status_code == 404

    def test_list_conversations_ordering(self):
        resp = client.post("/api/conversations", params={"title": "对话A"})
        id_a = resp.json()["id"]

        resp = client.post("/api/conversations", params={"title": "对话B"})
        id_b = resp.json()["id"]

        resp = client.get("/api/conversations")
        convs = resp.json()
        # 按 updated_at 降序
        assert convs[0]["id"] in (id_a, id_b)
        assert len(convs) >= 1

    def test_send_message_sync(self):
        resp = client.post("/api/conversations", params={"title": "测试发送"})
        conv_id = resp.json()["id"]

        resp = client.post(
            f"/api/conversations/{conv_id}/messages/sync",
            json={"message": "你好"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data

    def test_send_message_sync_nonexistent(self):
        resp = client.post(
            "/api/conversations/nonexistent/messages/sync",
            json={"message": "你好"},
        )
        assert resp.status_code == 404
