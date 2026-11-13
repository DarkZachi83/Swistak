# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Interfejs adaptera LLM v1 — niezależny od Ollamy i aplikacji PySide6."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Protocol, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .gateway import ToolSession


@dataclass(frozen=True)
class StreamEvent:
    kind: str  # delta | completed | tool_call | tool_result
    text: str = ""
    result: dict[str, Any] | None = None


class LLMProvider(Protocol):
    is_local: bool

    def health_check(self, model_id: str) -> bool: ...
    def list_models(self) -> list[str]: ...
    def get_capabilities(self, model_id: str) -> dict[str, Any]: ...
    def generate(self, task: dict[str, Any], model_id: str) -> dict[str, Any]: ...
    def stream(self, task: dict[str, Any], model_id: str) -> Iterator[StreamEvent]: ...
    def cancel(self, task_id: str) -> None: ...
    def run_tools(self, task: dict[str, Any], model_id: str,
                  session: ToolSession,
                  progress: Callable[[StreamEvent], None] | None = None) -> dict[str, Any]: ...
