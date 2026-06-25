"""出题 API 测试"""
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.auth import create_token, hash_password

client = TestClient(app)

_TEST_USER_ID = "quiz-test-user"


def setup_module():
    from datetime import datetime, timezone
    conn = get_db()
    conn.execute("DELETE FROM users")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (_TEST_USER_ID, "quizuser", hash_password("test1234"), now),
    )
    conn.commit()
    conn.close()


def _headers():
    return {"Authorization": f"Bearer {create_token(_TEST_USER_ID)}"}


class TestQuizAPI:
    def test_generate_quiz_too_short(self):
        resp = client.post(
            "/api/quiz/generate",
            json={"content": "太短了", "question_count": 3},
            headers=_headers(),
        )
        assert resp.status_code == 422

    def test_generate_quiz_valid(self):
        resp = client.post(
            "/api/quiz/generate",
            json={
                "content": "光合作用包括光反应和暗反应两个阶段。"
                           "光反应在类囊体膜上进行，将光能转化为 ATP 和 NADPH。"
                           "暗反应在叶绿体基质中进行。光反应需要光照，暗反应不需要。",
                "question_count": 3,
            },
            headers=_headers(),
        )
        assert resp.status_code == 200
        assert len(resp.content) > 0

    def test_generate_from_file_no_filename(self):
        resp = client.post(
            "/api/quiz/generate-from-file",
            files={"file": ("", b"", "application/octet-stream")},
            headers=_headers(),
        )
        assert resp.status_code == 422

    def test_generate_from_file_unsupported(self):
        resp = client.post(
            "/api/quiz/generate-from-file",
            files={"file": ("test.xyz", b"data", "application/octet-stream")},
            headers=_headers(),
        )
        assert resp.status_code == 400

    def test_generate_from_file_empty_content(self):
        resp = client.post(
            "/api/quiz/generate-from-file?question_count=3",
            files={"file": ("empty.txt", b"   ", "text/plain")},
            headers=_headers(),
        )
        assert resp.status_code == 400

    def test_generate_from_file_valid(self):
        resp = client.post(
            "/api/quiz/generate-from-file?question_count=3",
            files={
                "file": (
                    "ai.txt",
                    b"Artificial Intelligence is a branch of computer science. "
                    b"Machine learning is a core technology of AI. "
                    b"Deep learning uses multi-layer neural networks.",
                    "text/plain",
                )
            },
            headers=_headers(),
        )
        assert resp.status_code == 200
        assert len(resp.content) > 0
