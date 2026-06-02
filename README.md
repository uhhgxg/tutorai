# TutorAI — AI 智能学习助手

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个基于大语言模型的智能学习助手，支持**对话辅导**、**文档检索问答（RAG）**和**自动出题测试**。

## 功能特性

| 功能 | 说明 |
|------|------|
| 💬 智能对话辅导 | AI 老师多轮对话，支持流式输出，自动总结对话标题 |
| 📄 文档检索问答 | 上传 PDF/TXT/Markdown/代码文件，TF-IDF + LLM 精准问答 |
| 📝 自动出题 | 输入知识点或上传文档，生成选择题 + 答案解析 |
| 🔄 流式响应 | 基于 SSE 的实时文字输出体验 |
| 💾 持久化存储 | SQLite 保存对话历史和文档索引 |

## 技术栈

**后端:** Python 3.12+ / FastAPI / Uvicorn  
**前端:** Jinja2 模板 + 原生 JS + CSS（无前端构建工具）  
**AI:** OpenAI 兼容 API（支持 OpenAI / DeepSeek / 通义千问等）  
**检索:** scikit-learn TF-IDF + 余弦相似度  
**存储:** SQLite（零配置）  
**部署:** Docker / Docker Compose

## 项目结构

```
TutorAI/
├── app/
│   ├── main.py                 # FastAPI 应用入口
│   ├── config.py               # 配置管理（环境变量）
│   ├── database.py             # SQLite 数据库操作
│   ├── models/
│   │   └── __init__.py         # Pydantic 请求/响应模型
│   ├── routers/
│   │   ├── chat.py             # 对话管理 API
│   │   ├── document.py         # 文档上传/查询 API
│   │   ├── quiz.py             # 出题 API
│   │   └── pages.py            # 页面渲染
│   ├── services/
│   │   ├── llm_client.py       # LLM 调用封装
│   │   ├── retriever.py        # TF-IDF 检索器
│   │   └── document_parser.py  # PDF/TXT 解析
│   ├── templates/              # Jinja2 HTML 模板
│   └── static/                 # CSS + JavaScript
├── tests/                      # 单元测试
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── run.py                      # 一键启动
```

## 快速开始

### 1. 环境准备

```bash
# Python 3.12+
python --version

# 克隆项目
cd TutorAI
```

### 2. 配置 API Key

```bash
# 复制配置文件
cp .env.example .env

# 编辑 .env，填入你的 API Key
# LLM_API_KEY=sk-your-key-here
# LLM_BASE_URL=https://api.openai.com/v1  (或 DeepSeek: https://api.deepseek.com/v1)
# LLM_MODEL=gpt-4o-mini
```

### 3. 安装运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动（默认 http://localhost:8000）
python run.py
```

### 4. 使用 Docker

```bash
# 创建 .env 文件后
docker compose up -d

# 访问 http://localhost:8000
```

## API 文档

启动后访问 `http://localhost:8000/docs` 查看 Swagger API 文档。

### 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/conversations` | 获取对话列表 |
| POST | `/api/conversations` | 创建新对话 |
| GET | `/api/conversations/{id}/messages` | 获取对话消息 |
| POST | `/api/conversations/{id}/messages` | 发送消息（流式） |
| DELETE | `/api/conversations/{id}` | 删除对话 |
| POST | `/api/documents/upload` | 上传文档 |
| GET | `/api/documents` | 获取文档列表 |
| POST | `/api/documents/{id}/query` | 查询文档内容 |
| DELETE | `/api/documents/{id}` | 删除文档 |
| POST | `/api/quiz/generate` | 生成练习题 |

## 运行测试

```bash
pytest tests/ -v
```

## 支持的模型提供商

| 提供商 | LLM_BASE_URL |
|--------|-------------|
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 其他兼容 API | 自定义 URL |

## License

MIT License
