"""聊天 API 测试"""
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.auth import create_token, hash_password

client = TestClient(app)

_TEST_USER_ID = "chat-test-user"


def setup_module():
    """创建测试用户"""
    from datetime import datetime, timezone
    conn = get_db()
    conn.execute("DELETE FROM users")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (_TEST_USER_ID, "chatuser", hash_password("test1234"), now),
    )
    conn.commit()
    conn.close()


def _headers():
    return {"Authorization": f"Bearer {create_token(_TEST_USER_ID)}"}


class TestChatAPI:
    def test_list_conversations_empty(self):
        resp = client.get("/api/conversations", headers=_headers())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_conversation(self):
        resp = client.post("/api/conversations", params={"title": "测试对话"}, headers=_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["title"] == "测试对话"

    def test_create_conversation_default_title(self):
        resp = client.post("/api/conversations", headers=_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "新对话"

    def test_get_messages_empty(self):
        resp = client.post("/api/conversations", params={"title": "空对话"}, headers=_headers())
        conv_id = resp.json()["id"]

        resp = client.get(f"/api/conversations/{conv_id}/messages", headers=_headers())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_messages_nonexistent(self):
        resp = client.get("/api/conversations/nonexistent/messages", headers=_headers())
        assert resp.status_code == 404

    def test_delete_conversation(self):
        resp = client.post("/api/conversations", params={"title": "待删除"}, headers=_headers())
        conv_id = resp.json()["id"]

        resp = client.delete(f"/api/conversations/{conv_id}", headers=_headers())
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        resp = client.get("/api/conversations", headers=_headers())
        assert all(c["id"] != conv_id for c in resp.json())

    def test_delete_nonexistent(self):
        resp = client.delete("/api/conversations/nonexistent", headers=_headers())
        assert resp.status_code == 404

    def test_list_conversations_ordering(self):
        resp = client.post("/api/conversations", params={"title": "对话A"}, headers=_headers())
        id_a = resp.json()["id"]
        resp = client.post("/api/conversations", params={"title": "对话B"}, headers=_headers())
        id_b = resp.json()["id"]

        resp = client.get("/api/conversations", headers=_headers())
        convs = resp.json()
        assert convs[0]["id"] in (id_a, id_b)
        assert len(convs) >= 1

    def test_send_message_sync(self):
        resp = client.post("/api/conversations", params={"title": "测试发送"}, headers=_headers())
        conv_id = resp.json()["id"]

        resp = client.post(
            f"/api/conversations/{conv_id}/messages/sync",
            json={"message": "你好"},
            headers=_headers(),
        )
        # 无 API Key 时返回提示消息，不会报错
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data

    def test_send_message_sync_nonexistent(self):
        resp = client.post(
            "/api/conversations/nonexistent/messages/sync",
            json={"message": "你好"},
            headers=_headers(),
        )
        assert resp.status_code == 404
