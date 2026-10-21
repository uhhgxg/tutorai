"""TutorAI Agent Runtime.

对外只暴露运行时入口，具体的模型调用仍由 services 层负责。
"""

from app.agent.contracts import AgentResult, StreamEvent, TurnContext
from app.agent.orchestrator import TutorOrchestrator
from app.agent.registry import CapabilityRegistry, ToolRegistry

__all__ = [
    "AgentResult",
    "CapabilityRegistry",
    "StreamEvent",
    "ToolRegistry",
    "TutorOrchestrator",
    "TurnContext",
]
