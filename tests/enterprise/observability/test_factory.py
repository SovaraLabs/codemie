# Copyright 2026 EPAM Systems, Inc. ("EPAM")
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

"""Tests for observability provider factory."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from codemie.enterprise.observability.factory import (
    get_observability_provider,
    reset_provider,
)
from codemie.enterprise.observability.noop_provider import NoOpObservabilityProvider


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the provider singleton before and after each test."""
    reset_provider()
    yield
    reset_provider()


class TestFactoryDefaultBehavior:
    def test_returns_noop_when_provider_is_none(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "none")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)

        provider = get_observability_provider()
        assert isinstance(provider, NoOpObservabilityProvider)

    def test_returns_noop_when_provider_is_empty(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)

        provider = get_observability_provider()
        assert isinstance(provider, NoOpObservabilityProvider)

    def test_returns_noop_for_unknown_provider(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "unknown_provider")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)

        provider = get_observability_provider()
        assert isinstance(provider, NoOpObservabilityProvider)


class TestFactorySingleton:
    def test_returns_same_instance_on_multiple_calls(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "none")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)

        provider1 = get_observability_provider()
        provider2 = get_observability_provider()
        assert provider1 is provider2

    def test_reset_clears_singleton(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "none")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)

        provider1 = get_observability_provider()
        reset_provider()
        provider2 = get_observability_provider()
        assert provider1 is not provider2


class TestFactoryLangfuseBackwardCompat:
    def test_langfuse_traces_true_with_empty_provider_selects_langfuse(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)
        monkeypatch.setattr("codemie.enterprise.loader.HAS_LANGFUSE", True)

        with patch(
            "codemie.enterprise.observability.factory.LangfuseObservabilityProvider",
            create=True,
        ) as mock_cls:
            from codemie.enterprise.observability.langfuse_provider import LangfuseObservabilityProvider

            mock_cls.return_value = LangfuseObservabilityProvider.__new__(LangfuseObservabilityProvider)
            # Re-import to get a fresh factory call
            reset_provider()

        # Direct test: patch at the config level and call factory
        from codemie.enterprise.observability.factory import _create_provider

        provider = _create_provider()
        from codemie.enterprise.observability.langfuse_provider import LangfuseObservabilityProvider

        assert isinstance(provider, LangfuseObservabilityProvider)

    def test_langfuse_traces_true_without_enterprise_falls_back_to_noop(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)
        monkeypatch.setattr("codemie.enterprise.loader.HAS_LANGFUSE", False)

        provider = get_observability_provider()
        assert isinstance(provider, NoOpObservabilityProvider)


class TestFactoryLangfuseExplicit:
    def test_langfuse_provider_with_enterprise_installed(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "langfuse")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)
        monkeypatch.setattr("codemie.enterprise.loader.HAS_LANGFUSE", True)

        from codemie.enterprise.observability.langfuse_provider import LangfuseObservabilityProvider

        provider = get_observability_provider()
        assert isinstance(provider, LangfuseObservabilityProvider)

    def test_langfuse_provider_without_enterprise_falls_back_to_noop(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "langfuse")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)
        monkeypatch.setattr("codemie.enterprise.loader.HAS_LANGFUSE", False)

        provider = get_observability_provider()
        assert isinstance(provider, NoOpObservabilityProvider)


class TestFactoryPhoenix:
    def test_phoenix_provider_with_enterprise_installed(self, monkeypatch):
        import sys
        from types import ModuleType
        from unittest.mock import MagicMock

        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "phoenix")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)
        monkeypatch.setattr("codemie.enterprise.loader.HAS_PHOENIX", True)

        phoenix_config_mod = ModuleType("codemie_enterprise.phoenix.config")
        phoenix_config_mod.PhoenixConfig = MagicMock(name="PhoenixConfig")
        monkeypatch.setitem(sys.modules, "codemie_enterprise.phoenix.config", phoenix_config_mod)

        from codemie.enterprise.observability.phoenix_provider import PhoenixObservabilityProvider

        provider = get_observability_provider()
        assert isinstance(provider, PhoenixObservabilityProvider)

    def test_phoenix_provider_without_enterprise_falls_back_to_noop(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "phoenix")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)
        monkeypatch.setattr("codemie.enterprise.loader.HAS_PHOENIX", False)

        provider = get_observability_provider()
        assert isinstance(provider, NoOpObservabilityProvider)


class TestFactoryCaseInsensitive:
    def test_provider_name_is_case_insensitive(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "  NONE  ")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)

        provider = get_observability_provider()
        assert isinstance(provider, NoOpObservabilityProvider)

    def test_langfuse_name_case_insensitive(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "Langfuse")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)
        monkeypatch.setattr("codemie.enterprise.loader.HAS_LANGFUSE", True)

        from codemie.enterprise.observability.langfuse_provider import LangfuseObservabilityProvider

        provider = get_observability_provider()
        assert isinstance(provider, LangfuseObservabilityProvider)


class TestFactoryCreateProviderDirect:
    def test_unknown_provider_warning_contains_name(self, monkeypatch):
        from unittest.mock import patch

        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "custom_tracer")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)

        from codemie.enterprise.observability.factory import _create_provider

        with patch("codemie.configs.logger") as mock_logger:
            result = _create_provider()

        assert isinstance(result, NoOpObservabilityProvider)
        warning_calls = mock_logger.warning.call_args_list
        assert any("custom_tracer" in str(call) for call in warning_calls)

    def test_langfuse_backward_compat_logs_provider(self, monkeypatch):
        from unittest.mock import patch

        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)
        monkeypatch.setattr("codemie.enterprise.loader.HAS_LANGFUSE", True)

        from codemie.enterprise.observability.factory import _create_provider

        with patch("codemie.configs.logger") as mock_logger:
            result = _create_provider()

        from codemie.enterprise.observability.langfuse_provider import LangfuseObservabilityProvider

        assert isinstance(result, LangfuseObservabilityProvider)
        mock_logger.info.assert_called_once_with("Observability provider: Langfuse")

    def test_phoenix_provider_logs_provider_name(self, monkeypatch):
        import sys
        from types import ModuleType
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "phoenix")
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)
        monkeypatch.setattr("codemie.enterprise.loader.HAS_PHOENIX", True)

        phoenix_config_mod = ModuleType("codemie_enterprise.phoenix.config")
        phoenix_config_mod.PhoenixConfig = MagicMock(name="PhoenixConfig")
        monkeypatch.setitem(sys.modules, "codemie_enterprise.phoenix.config", phoenix_config_mod)

        from codemie.enterprise.observability.factory import _create_provider
        from codemie.enterprise.observability.phoenix_provider import PhoenixObservabilityProvider

        with patch("codemie.configs.logger") as mock_logger:
            result = _create_provider()

        assert isinstance(result, PhoenixObservabilityProvider)
        mock_logger.info.assert_called_once_with("Observability provider: Arize Phoenix")


class TestFactorySovara:
    def test_returns_sovara_when_sovara_langchain_is_installed(self, monkeypatch):
        from codemie.enterprise.observability.sovara_provider import SovaraObservabilityProvider

        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "sovara")
        with patch("importlib.util.find_spec", return_value=object()):
            provider = get_observability_provider()
        assert isinstance(provider, SovaraObservabilityProvider)

    def test_falls_back_to_noop_without_sovara_langchain(self, monkeypatch):
        monkeypatch.setattr("codemie.configs.config.OBSERVABILITY_PROVIDER", "sovara")
        with patch("importlib.util.find_spec", return_value=None):
            provider = get_observability_provider()
        assert isinstance(provider, NoOpObservabilityProvider)
