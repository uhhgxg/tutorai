"""数据库领域模块

按领域拆分为独立的 Repository，每个 Repo 只关注一张表的操作。
engine.py 负责连接管理和重试机制。
"""
