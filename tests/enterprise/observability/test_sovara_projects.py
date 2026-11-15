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

"""Check explicit provisioning and rename retries against the HTTP boundary."""

import json

import httpx
import pytest

from codemie.core.exceptions import ExtendedHTTPException
from codemie.enterprise.observability.sovara_projects import SovaraProjects, config
from codemie.enterprise.observability.sovara_provider import SovaraObservabilityProvider


@pytest.fixture
def project_api(monkeypatch, httpx_mock):
    monkeypatch.setattr(config, "SOVARA_SERVER_URL", "https://sovara.test")
    monkeypatch.setattr(config, "SOVARA_API_KEY", "synthetic-key")
    return SovaraProjects(), httpx_mock


@pytest.mark.parametrize("exists", [True, False])
def test_recording_explicitly_provisions_before_constructing_client(project_api, monkeypatch, exists):
    import sys
    import types
    from unittest.mock import Mock

    _, transport = project_api
    transport.add_response(method="GET", status_code=200 if exists else 404, json={"project_id": "p1"})
    if not exists:
        transport.add_response(method="POST", status_code=201, json={"project_id": "p1"})
    sdk = types.ModuleType("sovara")
    sdk.SovaraClient = Mock()
    monkeypatch.setitem(sys.modules, "sovara", sdk)
    provider = SovaraObservabilityProvider()
    provider._client("research")
    sdk.SovaraClient.assert_called_once_with(
        project_name="research", api_key="synthetic-key", base_url="https://sovara.test"
    )
    assert transport.get_requests()[0].headers["x-sovara-contract"] == "app-api"
    if not exists:
        assert json.loads(transport.get_requests()[1].content) == {"name": "research"}


def test_rename_retries_same_project_id_and_clears_both_client_names(project_api):
    _, transport = project_api
    transport.add_response(method="GET", json={"project_id": "p1"})
    transport.add_exception(httpx.ReadTimeout("synthetic"), method="PATCH")
    transport.add_response(method="PATCH", json={"project_id": "p1", "name": "new"})
    provider = SovaraObservabilityProvider()
    provider._clients = {"old": object(), "new": object()}
    with provider.project_rename_context("old", "new"):
        pass
    requests = transport.get_requests()
    assert str(requests[1].url) == str(requests[2].url) == "https://sovara.test/api/projects/p1"
    assert json.loads(requests[2].content) == {"name": "new", "expected_name": "old"}
    assert provider._clients == {}


@pytest.mark.parametrize("rollback_status", [200, 409])
def test_local_failure_compensates_or_reports_reconciliation(project_api, rollback_status):
    api, transport = project_api
    transport.add_response(method="GET", json={"project_id": "p1"})
    transport.add_response(method="PATCH", json={"project_id": "p1", "name": "new"})
    transport.add_response(method="PATCH", status_code=rollback_status, json={})
    with pytest.raises(ValueError if rollback_status == 200 else ExtendedHTTPException):
        with api.rename("old", "new"):
            raise ValueError("local transaction failed")
    assert json.loads(transport.get_requests()[-1].content) == {"name": "old", "expected_name": "new"}


def test_unprovisioned_project_rename_does_not_create_anything(project_api):
    api, transport = project_api
    transport.add_response(method="GET", status_code=404)
    with api.rename("old", "new"):
        pass
    assert len(transport.get_requests()) == 1


def test_provisioning_rejects_missing_permission(project_api):
    api, transport = project_api
    transport.add_response(method="GET", status_code=404)
    transport.add_response(method="POST", status_code=403)
    with pytest.raises(ExtendedHTTPException):
        api.ensure("research")


@pytest.mark.parametrize("status", [403, 409])
def test_rejected_rename_never_enters_local_mutation(project_api, status):
    api, transport = project_api
    transport.add_response(method="GET", json={"project_id": "p1"})
    transport.add_response(method="PATCH", status_code=status)
    with pytest.raises(ExtendedHTTPException):
        with api.rename("old", "new"):
            pytest.fail("Rejected rename must not mutate CodeMie")
    assert len(transport.get_requests()) == 2
