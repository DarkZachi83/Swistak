# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bezpieczne zadania AI, routing i anulaowanie; bez Tool Gateway i GUI."""
from __future__ import annotations

import threading
from contextlib import nullcontext
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from .contracts import sanitize_result, validate
from .gateway import ToolGateway, ToolSession
from .errors import AICoreError, ModelUnavailable, TaskCancelled, ToolGatewayPending
from .provider import StreamEvent
from .router import ModelRouter

ProgressCallback = Callable[[StreamEvent], None]


class AgentOrchestrator:
    """Jeden wykonawca domyślnie: brak równoległego obciążania GPU.

    TaskRequest pozostaje wspólną kopertą. W Etapie 1 zadania wymagające
    narzędzi są odrzucane zamiast symulować dostęp do SQLite.
    """

    def __init__(self, router: ModelRouter, *, max_workers: int = 1,
                 gateway: ToolGateway | None = None):
        if max_workers < 1 or max_workers > 4:
            raise ValueError("Nieprawidłowy limit równoległych zadań")
        self.router = router
        self.gateway = gateway
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="swistak-ai")
        self._lock = threading.RLock()
        self._futures: dict[str, Future[dict[str, Any]]] = {}
        self._recent_ids: deque[str] = deque(maxlen=4096)
        self._cancelled: set[str] = set()
        self._active: dict[str, object] = {}

    def _run(self, task: dict[str, Any], progress: ProgressCallback | None) -> dict[str, Any]:
        task_id = task["task_id"]
        with self._lock:
            if task_id in self._cancelled:
                raise TaskCancelled("Zadanie anulowano przed rozpoczęciem")
        provider, binding = self.router.select(task["role"])
        with self._lock:
            self._active[task_id] = provider
        session_context = (self.gateway.session(task) if task["allowed_tools"] else nullcontext(None))
        try:
            with session_context as session:
                if self._is_cancelled(task_id):
                    raise TaskCancelled("Zadanie zostało anulowane")
                try:
                    result = self._invoke(provider, binding.model_id, task, progress, session)
                except ModelUnavailable:
                    backup = self.router.fallback_main(task["role"])
                    if backup is None:
                        raise
                    provider, binding = backup
                    with self._lock:
                        self._active[task_id] = provider
                    if self._is_cancelled(task_id):
                        raise TaskCancelled("Zadanie zostało anulowane")
                    result = self._invoke(provider, binding.model_id, task, progress, session)
                if self._is_cancelled(task_id):
                    raise TaskCancelled("Wynik anulowanego zadania został odrzucony")
                return sanitize_result(
                    result, task, binding.model_id,
                    verifier=session.trusted_evidence if session else None,
                )
        finally:
            with self._lock:
                self._active.pop(task_id, None)

    @staticmethod
    def _invoke(provider, model_id: str, task: dict[str, Any],
                progress: ProgressCallback | None,
                session: ToolSession | None = None) -> dict[str, Any]:
        if session is not None:
            fn = getattr(provider, "run_tools", None)
            if fn is None:
                raise ModelUnavailable("Adapter nie obsługuje narzędzi")
            return fn(task, model_id, session, progress)
        if progress is None:
            return provider.generate(task, model_id)
        result = None
        for event in provider.stream(task, model_id):
            if event.kind == "completed":
                result = event.result
            progress(event)
        if result is None:
            raise AICoreError("Brak końcowego wyniku modelu")
        return result

    def _is_cancelled(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._cancelled

    def _forget_future(self, task_id: str, future: Future[dict[str, Any]]) -> None:
        with self._lock:
            if self._futures.get(task_id) is future:
                self._futures.pop(task_id, None)
            self._cancelled.discard(task_id)

    def submit(self, task: dict[str, Any],
               progress: ProgressCallback | None = None) -> Future[dict[str, Any]]:
        validate("TaskRequest", task)
        if task["allowed_tools"] and self.gateway is None:
            raise ToolGatewayPending("Brak skonfigurowanego Tool Gateway")
        task_id = task["task_id"]
        with self._lock:
            if task_id in self._futures or task_id in self._recent_ids:
                raise ValueError("Identyfikator zadania został już użyty")
            future = self._executor.submit(self._run, task, progress)
            self._futures[task_id] = future
            self._recent_ids.append(task_id)
            future.add_done_callback(lambda f, tid=task_id: self._forget_future(tid, f))
        return future

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            future = self._futures.get(task_id)
            if future is None or future.done():
                return False
            self._cancelled.add(task_id)
            provider = self._active.get(task_id)
        if provider is not None:
            provider.cancel(task_id)
        else:
            future.cancel()
        return True

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            ids = list(self._futures)
        for task_id in ids:
            self.cancel(task_id)
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def __enter__(self) -> "AgentOrchestrator":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.shutdown()
