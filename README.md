# TutorAI — AI 智能学习助手

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

基于大语言模型的 AI 学习助手，支持**智能对话辅导**、**RAG 文档问答**和**自动出题测试**。

---

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                     用户浏览器                           │
│          Jinja2 模板 + 原生 JS/CSS                       │
└──────────────┬──────────────────────────┬───────────────┘
               │ HTTP                     │ SSE Stream
┌──────────────▼──────────────────────────▼───────────────┐
│                   FastAPI 应用层                          │
│  ┌─────────┐ ┌───────────┐ ┌──────────┐ ┌───────────┐  │
│  │ Chat API│ │Document API│ │ Quiz API │ │ Pages API │  │
│  └────┬────┘ └─────┬─────┘ └────┬─────┘ └───────────┘  │
│       │            │            │                        │
│  ┌────▼────────────▼────────────▼──────────────────┐    │
│  │               Service 层                          │    │
│  │  llm_client   │  retriever   │  document_parser  │    │
│  │  (Agent+Tool) │ (ChromaDB)   │  (PDF/TXT/OCR)    │    │
│  └───────┬───────┴──────┬───────┴───────┬───────────┘    │
│          │              │               │                │
│  ┌───────▼──────────────▼───────────────▼───────────┐    │
│  │               Database 层                        │    │
│  │  SQLite: users / conversations / messages /      │    │
│  │          documents / document_chunks / quiz      │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### RAG 链路（核心面试点）

完整的文档检索问答流程分为 7 步：

```
① 上传文件 → ② 解析文本 → ③ 切分块
   (PDF/TXT)  (PyMuPDF/OCR)  (RecursiveCharSplitter)
                                    │
                                    ▼
④ 用户提问 ──→ ⑤ ChromaDB 向量检索 ──→ ⑥ 拼接上下文 ──→ ⑦ LLM 生成回答
                 (余弦相似度)      (Prompt 组装)    (Streaming/Agent)
```

每一步对应的代码位置：

| 步骤 | 功能 | 文件 | 关键函数 |
|------|------|------|----------|
| ① | 上传文件 | `app/routers/document.py` | `upload_document()` |
| ② | 解析文本 | `app/services/document_parser.py` | `parse_document()` |
| ③ | 切分文本块 | `app/services/document_parser.py` | `chunk_text()` |
| ④ | 用户提问 | `app/routers/document.py` | `query_document()` |
| ⑤ | 向量检索 | `app/services/retriever.py` | `search()` |
| ⑥ | 拼接上下文 | `app/services/llm_client.py` | `build_chat_messages()` |
| ⑦ | LLM 生成回答 | `app/services/llm_client.py` | `agent_chat()` / `agent_chat_stream()` |

## 技术栈

| 层级 | 技术 | 选型理由 |
|------|------|----------|
| **后端框架** | FastAPI + Uvicorn | 异步性能好，自动生成 Swagger 文档 |
| **前端** | Jinja2 模板 + 原生 JS/CSS | 零构建工具，快速迭代，够用不重 |
| **AI** | OpenAI 兼容 API（LangChain） | 支持 OpenAI / DeepSeek / 通义千问等 |
| **检索** | ChromaDB + sentence-transformers 向量检索 | 语义级匹配，支持中英文混搜 |
| **存储** | SQLite（PRAGMA foreign_keys=ON） | 零配置，文件级数据库 |
| **认证** | JWT + bcrypt | 无状态认证，用户数据隔离 |
| **部署** | Docker / Docker Compose | 一键部署，内含 OCR 引擎 |

## 功能特性

- **💬 智能对话辅导** — AI 老师多轮对话，支持 Agent 工具调用和流式输出，自动提取对话标题
- **📄 RAG 文档问答** — 上传 PDF/TXT/代码文件，ChromaDB 向量检索 + LLM 生成精准回答，用户数据隔离
- **📝 自动出题** — 输入知识点或上传文档，生成选择题/判断题/填空题/简答题 + 答案解析
- **🔐 用户系统** — JWT 注册/登录，所有数据按用户隔离（Row-Level Security）
- **🔄 流式响应** — 基于 SSE 的逐 token 实时输出
- **🧩 Agent 工具调用** — LLM 可自主调用 `retrieve_document` 工具检索文档

## 项目结构

```
app/
├── main.py                 # FastAPI 应用入口（生命周期、中间件、路由注册）
├── config.py               # 配置管理（Pydantic Settings + .env 文件）
├── database.py             # SQLite 建表与 CRUD 操作
├── auth.py                 # JWT 令牌生成/验证 + bcrypt 密码哈希
├── models/__init__.py      # Pydantic 请求/响应模型（含校验规则）
├── routers/
│   ├── chat.py             # 对话 CRUD + 流式/同步消息发送
│   ├── document.py         # 文档上传/检索/删除 API（RAG 入口）
│   ├── quiz.py             # 出题生成/保存/历史 API
│   └── pages.py            # 页面路由（首页、登录、注册、出题）
├── services/
│   ├── llm_client.py       # LLM 调用封装（对话/流式/Agent/出题）
│   ├── retriever.py        # ChromaDB 向量检索 + 语义匹配
│   ├── document_parser.py  # PDF(PyMuPDF+OCR)/TXT 文本提取
│   ├── tools.py            # LangChain Agent 工具定义
│   └── rate_limiter.py     # 请求频率限制
├── templates/              # Jinja2 HTML 模板
└── static/                 # CSS + JavaScript
```

## 快速开始

### 本地运行

```bash
# 1. 配置
cp .env.example .env
# 编辑 .env: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

# 2. 安装
pip install -r requirements.txt

# 3. 启动（默认 http://localhost:8000）
python run.py
```

### Docker 部署

```bash
# 配置 API Key
cp .env.example .env
# 编辑 .env

# 一键启动
docker compose up -d

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

## 测试

```bash
# 全部 44 个测试
pytest tests/ -v

# 单独测试模块
pytest tests/test_retriever.py -v    # 检索器测试
pytest tests/test_database.py -v     # 数据库测试
pytest tests/test_chat_api.py -v     # 聊天 API 测试
pytest tests/test_document_api.py -v # 文档 API 测试
pytest tests/test_quiz_api.py -v     # 出题 API 测试
```

## API 文档

启动后访问 `http://localhost:8000/docs` 查看 Swagger 文档。

### 核心接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| GET | `/api/conversations` | 对话列表 |
| POST | `/api/conversations/{id}/messages` | 发送消息（流式 SSE） |
| POST | `/api/documents/upload` | 上传文档 |
| POST | `/api/documents/{id}/query` | RAG 文档问答 |
| POST | `/api/quiz/generate` | 生成练习题 |
| GET | `/health` | 健康检查（Docker 用） |

## 支持的 LLM 提供商

| 提供商 | `LLM_BASE_URL` |
|--------|----------------|
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 其他兼容 API | 自定义 URL |

## License

MIT License
