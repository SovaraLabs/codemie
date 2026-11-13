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

"""Tests for the Sovara observability provider. Sovara is faked: sovara-langchain is optional."""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager, nullcontext
from unittest.mock import Mock, patch

import pytest

from codemie.enterprise.observability import sovara_provider
from codemie.enterprise.observability.base import ObservabilityProvider
from codemie.enterprise.observability.sovara_provider import SovaraObservabilityProvider


class FakeClient:
    """Records the scopes opened, with the project they were opened in."""

    def __init__(self, project_name, opened):
        self.project_name = project_name
        self.opened = opened

    def _scope(self, *entry):
        @contextmanager
        def scope():
            self.opened.append((self.project_name, *entry))
            yield

        return scope()

    def trace(self, name, *, trace_id, capture_logs):
        assert capture_logs is False
        return self._scope("trace", name, trace_id)

    def turn(self, *, turn_input):
        return self._scope("turn", turn_input)

    def subtrace(self, name):
        return self._scope("subtrace", name)


@pytest.fixture
def opened():
    return []


@pytest.fixture
def provider(opened, monkeypatch):
    """An initialized provider whose clients are fakes, one per project."""
    provider = SovaraObservabilityProvider()
    provider._enabled = True
    clients = {}
    monkeypatch.setattr(
        provider,
        "_client",
        lambda project: clients.setdefault(project or "codemie", FakeClient(project or "codemie", opened)),
    )
    monkeypatch.setattr(sovara_provider, "_short_retries", nullcontext)
    return provider


def agent_run(provider, name, **kwargs):
    kwargs.setdefault("session_id", "conv-1")
    return provider.get_run_context(trace_name=name, **kwargs)


class TestChat:
    def test_message_is_a_turn_of_its_conversation_trace_in_its_project(self, provider, opened):
        with agent_run(provider, "Helper", user_input="hello", project="payments"):
            pass

        assert opened == [("payments", "trace", "Helper", "codemie:chat:conv-1"), ("payments", "turn", "hello")]

    def test_run_inside_a_recorded_run_is_a_subtrace_in_the_parent_project(self, provider, opened):
        with agent_run(provider, "Coordinator", user_input="hi", project="payments"):
            with agent_run(provider, "Specialist", user_input="task", project="other"):
                pass

        assert opened[-1] == ("payments", "subtrace", "Specialist")

    def test_runs_after_a_finished_run_start_their_own_trace(self, provider, opened):
        with agent_run(provider, "First", user_input="a"):
            pass
        with agent_run(provider, "Second", user_input="b", session_id="conv-2"):
            pass

        assert ("codemie", "trace", "Second", "codemie:chat:conv-2") in opened

    def test_no_recording_without_a_conversation(self, provider, opened):
        with agent_run(provider, "Helper", session_id=None):
            pass

        assert opened == []


class TestWorkflow:
    def test_run_is_a_turn_and_agent_nodes_are_subtraces(self, provider, opened):
        run = provider.get_workflow_run_context(
            execution_id="exec-1", workflow_name="Release notes", project="payments", user_input="v2"
        )
        with run:
            with agent_run(provider, "Writer", user_input="task", workflow_execution_id="exec-1"):
                pass

        assert opened == [
            ("payments", "trace", "Release notes", "codemie:workflow:exec-1"),
            ("payments", "turn", "v2"),
            ("payments", "subtrace", "Writer"),
        ]

    def test_agent_node_outside_the_workflow_context_still_joins_its_execution(self, provider, opened):
        with agent_run(provider, "Writer", user_input="task", project="payments", workflow_execution_id="exec-1"):
            pass

        assert opened == [
            ("payments", "trace", "CodeMie workflow", "codemie:workflow:exec-1"),
            ("payments", "subtrace", "Writer"),
        ]


class TestFailOpen:
    def test_sovara_failure_runs_unrecorded(self, provider, monkeypatch):
        monkeypatch.setattr(provider, "_client", Mock(side_effect=ConnectionError("down")))
        with patch.object(sovara_provider, "logger") as logger:
            with agent_run(provider, "Helper", user_input="hello"):
                ran = True

        assert ran
        assert "error_type=ConnectionError" in logger.warning.call_args[0][0]

    def test_errors_from_the_run_propagate(self, provider):
        with pytest.raises(ValueError), agent_run(provider, "Helper", user_input="hello"):
            raise ValueError("agent failed")

    def test_disabled_provider_does_nothing(self, opened):
        provider = SovaraObservabilityProvider()
        model = object()

        with agent_run(provider, "Helper", user_input="hello"):
            pass
        with provider.get_workflow_run_context(execution_id="exec-1", workflow_name="W"):
            pass

        assert opened == []
        assert provider.wrap_chat_model(model) is model
        assert provider.should_trace_request(None) is False

    def test_model_sovara_cannot_wrap_is_used_unwrapped(self, provider, monkeypatch):
        model = object()
        fake = types.ModuleType("sovara_langchain")
        fake.wrap_chat_model = Mock(side_effect=TypeError("not a chat model"))
        monkeypatch.setitem(sys.modules, "sovara_langchain", fake)

        assert provider.wrap_chat_model(model) is model


class TestClients:
    def test_one_client_per_project_with_the_configured_token(self, monkeypatch):
        fake = types.ModuleType("sovara")
        fake.SovaraClient = Mock(side_effect=lambda **kwargs: object())
        monkeypatch.setitem(sys.modules, "sovara", fake)
        monkeypatch.setattr(sovara_provider.config, "SOVARA_AGENT_TOKEN", "token")
        provider = SovaraObservabilityProvider()

        payments = provider._client("payments")

        assert provider._client("payments") is payments
        assert provider._client("other") is not payments
        assert provider._client(None) is provider._client("codemie")
        fake.SovaraClient.assert_any_call(project_name="payments", agent_token="token")

    def test_per_request_override_disables_recording(self, provider):
        assert provider.should_trace_request({"observability_traces_enabled": False}) is False
        assert provider.should_trace_request({}) is True


class TestBaseDefaults:
    """Langfuse, Phoenix and NoOp inherit these hooks unchanged."""

    def test_run_context_defaults_to_the_trace_context(self):
        trace_ctx = nullcontext()
        provider = Mock(spec=ObservabilityProvider)
        provider.get_trace_context.return_value = trace_ctx

        result = ObservabilityProvider.get_run_context(
            provider, trace_name="A", user_id="u", session_id="s", tags=["t"], user_input="hi", project="p"
        )

        assert result is trace_ctx
        provider.get_trace_context.assert_called_once_with(trace_name="A", user_id="u", session_id="s", tags=["t"])

    def test_workflow_run_context_and_model_wrap_default_to_no_ops(self):
        provider = Mock(spec=ObservabilityProvider)
        model = object()

        assert isinstance(
            ObservabilityProvider.get_workflow_run_context(provider, execution_id="e", workflow_name="W"), nullcontext
        )
        assert ObservabilityProvider.wrap_chat_model(provider, model) is model
