"""JSON 结构化日志配置 —— 便于生产环境日志聚合与检索"""

import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    """以 JSON 格式输出日志，每条一行，兼容 ELK / Loki 等日志系统"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "module": record.module,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exc"] = str(record.exc_info[1])
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    """应用入口调用一次，配置根 logger 为 JSON 格式输出"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(handlers=[handler], level=level, force=True)
