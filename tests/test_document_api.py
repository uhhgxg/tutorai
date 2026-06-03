"""文档 API 测试"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestDocumentAPI:
    def test_list_documents_empty(self):
        resp = client.get("/api/documents")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_upload_txt(self):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("test.txt", b"this is test document content", "text/plain")},
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
        )
        assert resp.status_code == 422

    def test_upload_unsupported_format(self):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("test.xyz", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "不支持" in resp.json()["detail"]

    def test_query_nonexistent_document(self):
        resp = client.post(
            "/api/documents/nonexistent/query",
            json={"question": "hello", "top_k": 3},
        )
        assert resp.status_code == 404

    def test_delete_document(self):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("delete_me.txt", b"document to delete", "text/plain")},
        )
        doc_id = resp.json()["id"]

        resp = client.delete(f"/api/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        resp = client.get("/api/documents")
        assert all(d["id"] != doc_id for d in resp.json())

    def test_delete_nonexistent(self):
        resp = client.delete("/api/documents/nonexistent")
        assert resp.status_code == 404
