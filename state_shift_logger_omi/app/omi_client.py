from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class OmiClient:
    def __init__(self):
        self.app_id = settings.omi_app_id
        self.api_key = settings.omi_api_key
        self.base_url = settings.omi_api_base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.api_key)

    async def create_memory(self, uid: str, content: str, tags: list[str] | None = None) -> bool:
        if not self.configured or not uid:
            return False

        url = f"{self.base_url}/v2/integrations/{self.app_id}/user/memories"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"uid": uid}
        payload: dict[str, Any] = {
            "memories": [
                {
                    "content": content,
                    "tags": tags or ["state_shift_logger", "possible_marker"],
                }
            ],
            "text_source": "other",
            "text_source_spec": "state_shift_logger",
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, headers=headers, params=params, json=payload)
            response.raise_for_status()
            return True
