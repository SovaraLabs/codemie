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

"""Observability provider factory.

Reads OBSERVABILITY_PROVIDER config and returns the appropriate provider singleton.
Includes backward-compatibility logic: if LANGFUSE_TRACES=True and
OBSERVABILITY_PROVIDER is unset/none, returns LangfuseObservabilityProvider.
"""

from __future__ import annotations

from .base import ObservabilityProvider

_provider: ObservabilityProvider | None = None


def get_observability_provider() -> ObservabilityProvider:
    """Return the active observability provider singleton.

    Provider selection priority:
    1. OBSERVABILITY_PROVIDER config value ("langfuse" | "phoenix" | "sovara" | "none")
    2. Backward-compat: if OBSERVABILITY_PROVIDER unset/none AND LANGFUSE_TRACES=True → langfuse
    3. Default: NoOpObservabilityProvider

    Returns:
        ObservabilityProvider instance (never None — falls back to NoOp)
    """
    global _provider
    if _provider is not None:
        return _provider

    _provider = _create_provider()
    return _provider


def reset_provider() -> None:
    """Reset the provider singleton. Use only in tests to switch providers between test cases."""
    global _provider
    _provider = None


def _create_provider() -> ObservabilityProvider:  # noqa: PLR0911 - one return per provider
    """Create a new provider instance based on current config."""
    from codemie.configs import config, logger

    from .noop_provider import NoOpObservabilityProvider

    provider_name = (config.OBSERVABILITY_PROVIDER or "").strip().lower()

    # Backward-compat: treat LANGFUSE_TRACES=True as implicit OBSERVABILITY_PROVIDER=langfuse
    if provider_name in ("", "none") and config.LANGFUSE_TRACES:
        provider_name = "langfuse"

    if provider_name == "langfuse":
        from codemie.enterprise.loader import HAS_LANGFUSE

        if not HAS_LANGFUSE:
            logger.warning(
                "OBSERVABILITY_PROVIDER=langfuse but codemie_enterprise is not installed. "
                "Falling back to NoOp provider."
            )
            return NoOpObservabilityProvider()

        from .langfuse_provider import LangfuseObservabilityProvider

        logger.info("Observability provider: Langfuse")
        return LangfuseObservabilityProvider()

    if provider_name == "phoenix":
        from codemie.enterprise.loader import HAS_PHOENIX

        if not HAS_PHOENIX:
            logger.warning(
                "OBSERVABILITY_PROVIDER=phoenix but codemie_enterprise[phoenix] is not installed. "
                "Falling back to NoOp provider."
            )
            return NoOpObservabilityProvider()

        from .phoenix_provider import PhoenixObservabilityProvider

        logger.info("Observability provider: Arize Phoenix")
        return PhoenixObservabilityProvider()

    if provider_name == "sovara":
        from importlib.util import find_spec  # noqa: PLC0415 - like the other providers' branches

        if find_spec("sovara_langchain") is None:
            logger.warning(
                "OBSERVABILITY_PROVIDER=sovara but sovara-langchain is not installed. Falling back to NoOp provider."
            )
            return NoOpObservabilityProvider()

        from .sovara_provider import SovaraObservabilityProvider  # noqa: PLC0415 - loaded only when selected

        logger.info("Observability provider: Sovara")
        return SovaraObservabilityProvider()

    if provider_name not in ("", "none"):
        from codemie.configs import logger as log

        log.warning(f"Unknown OBSERVABILITY_PROVIDER value: '{provider_name}'. Using NoOp provider.")

    return NoOpObservabilityProvider()
