from collections.abc import Generator
from typing import Any, Optional

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class PowerdrillChatTool(Tool):
    _sessions: dict[str, str] = {}  # user_id -> session_id mapping

    def _get_session(self, *, user_id: str, headers: dict[str, str], base_url: str) -> str:
        """Get or create a session for the user"""
        # NO lock protected
        if user_id in self._sessions:
            return self._sessions[user_id]

        # Create new session
        url = f"{base_url}/team/sessions"
        payload = {
            "name": f"Dify session for {user_id}",
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
            datasource_id: Optional[str],
            with_citation: bool,
            headers: dict[str, str],
            base_url: str,
    ) -> dict[str, Any]:
        """Create a new job (chat) in the session"""
        url = f"{base_url}/team/jobs"
        
        # Split datasource_id by comma if given
        datasource_id_list: list[str] = datasource_id.split(",") if datasource_id else []
        # trim the datasource_id_list
        datasource_id_list = [ds_id.strip() for ds_id in datasource_id_list]

        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "dataset_id": dataset_id,
            "datasource_ids": datasource_id_list if len(datasource_id_list) > 0 else None,
            "stream": False,
            "question": question,
            "output_language": "AUTO",
            "custom_options": {
                "with_citation": with_citation
            },
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
            "dataset_id"
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
        datasource_id: Optional[str] = tool_parameters.get("datasource_id")
        with_citation: bool = tool_parameters.get("with_citation", False)

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
            with_citation=with_citation,
            headers=headers,
            base_url=base_url,
        )

        # Process response
        blocks: list[dict[str, Any]] = job_response.get("blocks", [])

        citations: list[str] = []
        for block in blocks:
            if block['type'] == 'MESSAGE':
                yield self.create_text_message(text=block.get("content", ""))
            elif block['type'] == 'SOURCES' and with_citation:
                content: list[dict[str, str]] = block.get("content", [])
                for source_dict in content:
                    if source := source_dict.get("source"):
                        citations.append(source)
            elif block['type'] == 'IMAGE':
                content: dict[str, str] = block.get("content", {})
                if url := content.get("url"):
                    yield self.create_image_message(image_url=url)
            else:
                # TODO: Handle other block types
                pass
        
        if citations:
            yield self.create_text_message(text="\n\nCitations:")
            for i, citation in enumerate(citations):
                yield self.create_text_message(text=f"\n{i+1}. {citation}")

