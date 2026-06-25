"""文档 API 测试"""
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.auth import create_token, hash_password

client = TestClient(app)

_TEST_USER_ID = "doc-test-user"


def setup_module():
    from datetime import datetime, timezone
    conn = get_db()
    conn.execute("DELETE FROM users")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (_TEST_USER_ID, "docuser", hash_password("test1234"), now),
    )
    conn.commit()
    conn.close()


def _headers():
    return {"Authorization": f"Bearer {create_token(_TEST_USER_ID)}"}


class TestDocumentAPI:
    def test_list_documents_empty(self):
        resp = client.get("/api/documents", headers=_headers())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_upload_txt(self):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("test.txt", b"this is test document content", "text/plain")},
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["filename"] == "test.txt"
        assert data["chunk_count"] >= 1

    def test_upload_empty_filename(self):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("", b"", "application/octet-stream")},
            headers=_headers(),
        )
        assert resp.status_code == 422

    def test_upload_unsupported_format(self):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("test.xyz", b"data", "application/octet-stream")},
            headers=_headers(),
        )
        assert resp.status_code == 400
        assert "不支持" in resp.json()["detail"]

    def test_query_nonexistent_document(self):
        resp = client.post(
            "/api/documents/nonexistent/query",
            json={"question": "hello", "top_k": 3},
            headers=_headers(),
        )
        assert resp.status_code == 404

    def test_delete_document(self):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("delete_me.txt", b"document to delete", "text/plain")},
            headers=_headers(),
        )
        doc_id = resp.json()["id"]

        resp = client.delete(f"/api/documents/{doc_id}", headers=_headers())
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        resp = client.get("/api/documents", headers=_headers())
        assert all(d["id"] != doc_id for d in resp.json())

    def test_delete_nonexistent(self):
        resp = client.delete("/api/documents/nonexistent", headers=_headers())
        assert resp.status_code == 404
