# Copyright 2026 EPAM Systems, Inc. (“EPAM”)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Sovara observability provider: records CodeMie runs and adds Sovara lessons to model requests.

- A conversation is a trace (``codemie:chat:<conversation_id>``) in the Sovara project named
  after its CodeMie project; each message is a turn.
- A workflow execution is a trace (``codemie:workflow:<execution_id>``); each run or resume is a
  turn, and each agent-node run is a subtrace named after its assistant.
- An agent run inside another recorded run is a subtrace of it, in the same project.

Model calls are recorded by wrapping each chat model with ``sovara_langchain.wrap_chat_model``,
which also adds the lessons; tool calls through LangChain's tool execution. HTTP clients are not
patched. Sovara failures never fail a CodeMie run: it continues unrecorded.

``sovara-langchain`` is an optional package: the factory selects this provider only when it is
installed, and it is imported here only then.
"""

# ruff: noqa: ARG002, PLR0913, PLR0917 - ObservabilityProvider fixes these signatures; Sovara ignores
# the arguments it does not record.

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager, nullcontext
from contextvars import ContextVar
from typing import Any

from codemie.configs import config, logger

from .base import ObservabilityProvider

# Client recording the innermost active run, so nested runs join its trace and project.
_active_client: ContextVar[Any | None] = ContextVar("sovara_active_client", default=None)


def _short_retries() -> AbstractContextManager:
    """Retry Sovara for a few seconds only, so a Sovara outage never holds a CodeMie request."""
    from sovara.integration import short_retries  # noqa: PLC0415 - optional package

    return short_retries()


@contextmanager
def _activate(client: Any) -> Iterator[None]:
    token = _active_client.set(client)
    try:
        yield
    finally:
        try:
            _active_client.reset(token)
        except ValueError:
            # Exited in another context (e.g. a stream closed by a different task).
            _active_client.set(None)


def _warn_unrecorded(exc: Exception) -> None:
    logger.warning(f"Sovara recording unavailable; continuing unrecorded. error_type={type(exc).__name__}")


class SovaraObservabilityProvider(ObservabilityProvider):
    """Records agent runs and workflow executions in Sovara, one Sovara project per CodeMie project."""

    def __init__(self) -> None:
        self._enabled = False
        self._clients: dict[str, Any] = {}
        self._lock = threading.Lock()

    def initialize(self) -> None:
        try:
            import sovara_langchain  # noqa: PLC0415 - optional package

            # Records LangChain tool calls; model calls are recorded by wrap_chat_model.
            sovara_langchain.instrument_tools()
            self._enabled = True
            logger.info("Sovara observability provider initialized")
        except Exception as exc:
            logger.warning(f"Sovara observability provider disabled. error_type={type(exc).__name__}")

    def shutdown(self) -> None:
        if not self._enabled:
            return
        try:
            from sovara.integration import flush_recordings  # noqa: PLC0415 - optional package

            flush_recordings()
        except Exception as exc:
            logger.warning(f"Sovara flush on shutdown failed. error_type={type(exc).__name__}")

    def is_enabled(self) -> bool:
        return self._enabled

    def get_callback_handler(self) -> Any | None:
        # Calls are recorded by the model wrapper and tool instrumentation, not by callbacks.
        return None

    def create_workflow_trace_context(
        self,
        execution_id: str,
        workflow_id: str | None,
        workflow_name: str,
        user_id: str | None,
        session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Any | None:
        # The workflow trace is opened by get_workflow_run_context around the run itself.
        return None

    def get_workflow_trace_context(self, execution_id: str) -> Any | None:
        return None

    def clear_workflow_trace_context(self, execution_id: str) -> bool:
        return False

    def build_agent_metadata(
        self,
        agent_name: str,
        conversation_id: str,
        llm_model: str,
        username: str | None = None,
        tags: list[str] | None = None,
        trace_context: Any | None = None,
    ) -> dict:
        return {}

    def should_trace_request(self, request_metadata: dict | None) -> bool:
        if not self._enabled:
            return False
        override = (request_metadata or {}).get("observability_traces_enabled")
        return True if override is None else bool(override)

    def make_observe_decorator(self) -> Any:
        def observe(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001 - accepts observe(name=...) and ignores it
            return lambda fn: fn

        return observe

    def wrap_chat_model(self, llm: Any) -> Any:
        if not self._enabled:
            return llm
        try:
            from sovara_langchain import wrap_chat_model  # noqa: PLC0415 - optional package

            return wrap_chat_model(llm)
        except Exception as exc:
            logger.warning(f"Sovara cannot wrap this model; using it unrecorded. error_type={type(exc).__name__}")
            return llm

    def get_run_context(  # noqa: PLR0913 - ObservabilityProvider.get_run_context signature
        self,
        *,
        trace_name: str,
        user_id: str | None = None,  # noqa: ARG002 - not part of the Sovara trace
        session_id: str | None = None,
        tags: list[str] | None = None,  # noqa: ARG002 - not part of the Sovara trace
        user_input: str | None = None,
        project: str | None = None,
        workflow_execution_id: str | None = None,
    ) -> AbstractContextManager:
        if not (self._enabled and session_id):
            return nullcontext()
        run = {
            "agent_name": trace_name,
            "conversation_id": session_id,
            "user_input": user_input,
            "project": project,
            "workflow_execution_id": workflow_execution_id,
        }
        return self._recording(self._enter_agent_run, run)

    def get_workflow_run_context(
        self,
        *,
        execution_id: str,
        workflow_name: str,
        project: str | None = None,
        user_input: str | None = None,
    ) -> AbstractContextManager:
        if not (self._enabled and execution_id):
            return nullcontext()
        run = {
            "execution_id": execution_id,
            "workflow_name": workflow_name,
            "project": project,
            "user_input": user_input,
        }
        return self._recording(self._enter_workflow_run, run)

    @contextmanager
    def _recording(self, enter, run: dict[str, Any]) -> Iterator[None]:
        with ExitStack() as stack:
            try:
                stack.enter_context(_short_retries())
                enter(stack, run)
            except Exception as exc:
                _warn_unrecorded(exc)
            yield

    def _enter_agent_run(self, stack: ExitStack, run: dict[str, Any]) -> None:
        agent_name = run["agent_name"]
        parent = _active_client.get()
        if parent is not None:
            stack.enter_context(parent.subtrace(agent_name))
            return
        client = self._client(run["project"])
        if workflow_execution_id := run["workflow_execution_id"]:
            # An agent node outside the workflow's context (e.g. on a worker thread) still joins it.
            trace_id = f"codemie:workflow:{workflow_execution_id}"
            stack.enter_context(client.trace("CodeMie workflow", trace_id=trace_id, capture_logs=False))
            stack.enter_context(client.subtrace(agent_name))
        else:
            # capture_logs=False: concurrent requests share the process's stdout and stderr.
            trace_id = f"codemie:chat:{run['conversation_id']}"
            stack.enter_context(client.trace(agent_name, trace_id=trace_id, capture_logs=False))
            stack.enter_context(client.turn(turn_input=run["user_input"]))
        stack.enter_context(_activate(client))

    def _enter_workflow_run(self, stack: ExitStack, run: dict[str, Any]) -> None:
        parent = _active_client.get()
        if parent is not None:
            stack.enter_context(parent.subtrace(run["workflow_name"]))
            return
        client = self._client(run["project"])
        trace_id = f"codemie:workflow:{run['execution_id']}"
        stack.enter_context(client.trace(run["workflow_name"], trace_id=trace_id, capture_logs=False))
        stack.enter_context(client.turn(turn_input=run["user_input"]))
        stack.enter_context(_activate(client))

    def _client(self, project: str | None) -> Any:
        """Return the Sovara client for a CodeMie project, created on first use."""
        name = (project or "").strip() or config.SOVARA_DEFAULT_PROJECT
        with self._lock:
            client = self._clients.get(name)
            if client is None:
                from sovara import SovaraClient  # noqa: PLC0415 - optional package

                client = SovaraClient(project_name=name, agent_token=config.SOVARA_AGENT_TOKEN)
                self._clients[name] = client
        return client
