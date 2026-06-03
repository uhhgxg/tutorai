"""出题 API 测试"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestQuizAPI:
    def test_generate_quiz_too_short(self):
        """少于 50 字应校验通过（Pydantic 层）但内容太短"""
        resp = client.post(
            "/api/quiz/generate",
            json={"content": "太短了", "question_count": 3},
        )
        # Pydantic min_length=50 校验
        assert resp.status_code == 422

    def test_generate_quiz_valid(self):
        resp = client.post(
            "/api/quiz/generate",
            json={
                "content": "光合作用包括光反应和暗反应两个阶段。"
                           "光反应在类囊体膜上进行，将光能转化为 ATP 和 NADPH。"
                           "暗反应在叶绿体基质中进行，利用光反应产生的 ATP 和 NADPH 将 CO₂ 固定为有机物。"
                           "光反应需要光照，暗反应不需要光照。"
                           "光合作用的化学方程式是 6CO₂ + 6H₂O → C₆H₁₂O₆ + 6O₂。",
                "question_count": 3,
            },
        )
        assert resp.status_code == 200
        # 流式响应，内容非空
        assert len(resp.content) > 0

    def test_generate_from_file_no_filename(self):
        resp = client.post(
            "/api/quiz/generate-from-file",
            files={"file": ("", b"", "application/octet-stream")},
        )
        assert resp.status_code == 422

    def test_generate_from_file_unsupported(self):
        resp = client.post(
            "/api/quiz/generate-from-file",
            files={"file": ("test.xyz", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_generate_from_file_empty_content(self):
        """上传空内容的文件应报错"""
        resp = client.post(
            "/api/quiz/generate-from-file?question_count=3",
            files={"file": ("empty.txt", b"   ", "text/plain")},
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
        )
        assert resp.status_code == 200
        assert len(resp.content) > 0
