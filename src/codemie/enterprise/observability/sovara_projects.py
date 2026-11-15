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

"""Call Sovara's explicit project API without changing the recording SDK."""

from contextlib import contextmanager
from http import HTTPStatus
from collections.abc import Iterator
from urllib.parse import quote

import httpx

from codemie.configs import config, logger
from codemie.core.exceptions import ExtendedHTTPException


MAX_ATTEMPTS = 3


class SovaraUnavailable(ExtendedHTTPException):
    """Report a transport failure whose remote write outcome may be unknown."""


class SovaraProjects:
    """Resolve names and coordinate project renames without a persisted ID mapping."""

    def _request(self, method: str, path: str = "", **kwargs) -> httpx.Response:
        if not config.SOVARA_SERVER_URL or not config.SOVARA_API_KEY:
            raise ExtendedHTTPException(code=503, message="Sovara project API is not configured")
        headers = {
            "x-sovara-agent-token": config.SOVARA_API_KEY,
            "x-sovara-contract": "app-api",
            "x-sovara-contract-version": "6",
        }
        with httpx.Client(base_url=config.SOVARA_SERVER_URL.rstrip("/"), headers=headers, timeout=3.0) as client:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    response = client.request(method, "/api/projects" + path, **kwargs)
                except httpx.TransportError:
                    if attempt == MAX_ATTEMPTS - 1:
                        break
                    continue
                if (
                    response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
                    and response.status_code != HTTPStatus.TOO_MANY_REQUESTS
                ):
                    return response
        raise SovaraUnavailable(code=503, message="Sovara project API is unavailable; retry the operation")

    def _resolve(self, name: str) -> str | None:
        response = self._request("GET", "/resolve", params={"name": name})
        if response.status_code == HTTPStatus.NOT_FOUND:
            return None
        self._require_success(response)
        try:
            project_id = response.json()["project_id"]
            if isinstance(project_id, str) and project_id:
                return project_id
        except (ValueError, KeyError, TypeError):
            pass
        raise ExtendedHTTPException(code=503, message="Sovara returned invalid project metadata")

    @staticmethod
    def _require_success(response: httpx.Response) -> None:
        if not response.is_success:
            raise ExtendedHTTPException(
                code=409 if response.status_code == HTTPStatus.CONFLICT else 503,
                message="Sovara rejected the project operation; check project names and API key permissions",
            )

    def ensure(self, name: str) -> None:
        """Explicitly create a missing project, resolving concurrent first-use creation."""
        if self._resolve(name) is not None:
            return
        response = self._request("POST", json={"name": name})
        if response.status_code == HTTPStatus.CONFLICT and self._resolve(name) is not None:
            return
        self._require_success(response)

    def _rename(self, project_id: str, old_name: str, new_name: str) -> None:
        self._require_success(
            self._request("PATCH", "/" + quote(project_id, safe=""), json={"name": new_name, "expected_name": old_name})
        )

    @contextmanager
    def rename(self, old_name: str, new_name: str) -> Iterator[None]:
        """Rename before the local commit; attempt compensation if the transaction fails.

        Keep the resolved ID only for this operation, so transport retries cannot target
        a project that subsequently reuses the old name. Failed compensation requires
        operator reconciliation; two independent databases cannot commit atomically.
        """
        project_id = self._resolve(old_name)
        if project_id is None:
            yield
            return
        try:
            self._rename(project_id, old_name, new_name)
        except SovaraUnavailable:
            self._restore(project_id, new_name, old_name)
            raise
        try:
            yield
        except BaseException:
            self._restore(project_id, new_name, old_name)
            raise

    def _restore(self, project_id: str, new_name: str, old_name: str) -> None:
        try:
            self._rename(project_id, new_name, old_name)
        except Exception as exc:
            logger.error(f"Sovara project rename requires reconciliation. error_type={type(exc).__name__}")
            raise ExtendedHTTPException(
                code=503, message="Project rename requires reconciliation with Sovara before retrying"
            ) from None
