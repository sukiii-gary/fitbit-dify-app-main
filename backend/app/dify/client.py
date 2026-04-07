from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class DifyClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def run_workflow(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str, str | None]:
        if not self.settings.dify_api_key:
            return (
                {
                    "message": "Dify API key is empty. Request was assembled but not sent.",
                },
                "skipped",
                None,
            )

        try:
            response = httpx.post(
                self._build_url(self.settings.dify_workflow_endpoint),
                headers=self._headers(),
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            return (
                {
                    "message": "Dify workflow request failed with a non-2xx response.",
                    "status_code": exc.response.status_code,
                    "response_text": exc.response.text[:2000],
                },
                "error",
                None,
            )
        except httpx.HTTPError as exc:
            return (
                {
                    "message": "Dify workflow request failed before a valid response was received.",
                    "error_type": exc.__class__.__name__,
                    "details": str(exc),
                },
                "error",
                None,
            )

        workflow_run_id = (
            data.get("workflow_run_id")
            or data.get("task_id")
            or data.get("data", {}).get("id")
            or data.get("data", {}).get("workflow_run_id")
        )
        return data, "sent", workflow_run_id

    def get_workflow_parameters(self) -> tuple[dict[str, Any], str]:
        if not self.settings.dify_api_key:
            return {"message": "Dify API key is empty."}, "skipped"

        try:
            response = httpx.get(
                self._build_url("/parameters"),
                headers=self._headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json(), "ok"
        except httpx.HTTPStatusError as exc:
            return {
                "message": "Fetching Dify workflow parameters failed with a non-2xx response.",
                "status_code": exc.response.status_code,
                "response_text": exc.response.text[:2000],
            }, "error"
        except httpx.HTTPError as exc:
            return {
                "message": "Fetching Dify workflow parameters failed before a valid response was received.",
                "error_type": exc.__class__.__name__,
                "details": str(exc),
            }, "error"

    def _build_url(self, path: str) -> str:
        return f"{self.settings.dify_base_url.rstrip('/')}{path}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.dify_api_key}",
            "Content-Type": "application/json",
        }


def extract_workflow_outputs(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data")
    if isinstance(data, dict):
        outputs = data.get("outputs")
        if isinstance(outputs, dict):
            return outputs

    outputs = result.get("outputs")
    if isinstance(outputs, dict):
        return outputs

    return result
