from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class PowerdrillChatTool(Tool):
    _sessions: dict[str, str] = {}

    def _get_session(self, *, user_id: str, headers: dict[str, str], base_url: str) -> str:
        """Get or create a session for the user"""
        # NO lock protected
        if user_id in self._sessions:
            return self._sessions[user_id]

        # Create new session
        url = f"{base_url}/team/sessions"
        payload = {
            "name": f"Session for {user_id}",
            "user_id": user_id,
            "output_language": "AUTO",
            "job_mode": "AUTO",
            "max_contextual_job_history": 10,
        }

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        print(f"url: {url}, payload: {payload}, response: {response.json()}")
        session_id = response.json()["data"]["id"]
        self._sessions[user_id] = session_id
        return session_id

    def _create_job(
            self,
            *,
            session_id: str,
            question: str,
            user_id: str,
            dataset_id: str,
            datasource_id: str,
            headers: dict[str, str],
            base_url: str
    ) -> dict[str, Any]:
        """Create a new job (chat) in the session"""
        url = f"{base_url}/team/jobs"

        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "dataset_id": dataset_id,
            "datasource_ids": [datasource_id],
            "stream": False,
            "question": question,
            "output_language": "AUTO",
            "job_mode": "AUTO"
        }

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"url: {url}, payload: {payload}, response: {response.json()}")

        return response.json()["data"]
        
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        # The user_id param is the dify user, not the Powerdrill user, so it is not used for now
        # Validate required parameters
        required_params = [
            "api_key", "base_url", "user_id", "question",
            "dataset_id", "datasource_id"
        ]

        for param in required_params:
            if not tool_parameters.get(param):
                return ToolInvokeMessage(
                    message=f"Missing required parameter: {param}",
                    message_type="error"
                )

        # Extract parameters
        powerdrill_user_id: str = tool_parameters["user_id"]
        api_key: str = tool_parameters["api_key"]
        base_url: str = tool_parameters["base_url"]
        question: str = tool_parameters["question"]
        dataset_id: str = tool_parameters["dataset_id"]
        datasource_id: str = tool_parameters["datasource_id"]

        # Prepare headers
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "x-pd-api-key": api_key
        }

        # Get or create session
        session_id = self._get_session(
            user_id=powerdrill_user_id,
            headers=headers,
            base_url=base_url
        )

        # Create a job (chat) in the session
        job_response = self._create_job(
            session_id=session_id,
            question=question,
            user_id=powerdrill_user_id,
            dataset_id=dataset_id,
            datasource_id=datasource_id,
            headers=headers,
            base_url=base_url
        )

        # Process response
        blocks: list[dict[str, Any]] = job_response.get("blocks", [])

        for block in blocks:
            # TODO: handle other block types
            if block['type'] == 'MESSAGE':
                yield self.create_text_message(text=block.get("content", ""))

