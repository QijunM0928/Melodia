from .tools import ToolExecutor, TOOL_SCHEMAS

__all__ = ["Agent", "ToolExecutor", "TOOL_SCHEMAS"]


def __getattr__(name: str):
    if name == "Agent":
        from .agent import Agent

        return Agent
    raise AttributeError(name)
