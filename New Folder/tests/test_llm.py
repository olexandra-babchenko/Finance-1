"""OpenRouter interpreter tests with no live API requests."""

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from llm import OpenRouterClient  # noqa: E402


class UnsupportedJsonMode(Exception):
    status_code = 400


class OpenRouterClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = OpenRouterClient("test-key", "openrouter/free")
        self.fields = [
            {"field": "full_name", "required": True, "goal": "Get full name"}
        ]

    @staticmethod
    def response(content):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    @staticmethod
    def valid_json():
        return json.dumps(
            {
                "intent": "general",
                "extracted_fields": {},
                "answers_pending_field": False,
                "answer_quality": "not_answered",
                "side_question": None,
                "recommended_action": "clarify_intent",
                "followup_goal": None,
            }
        )

    async def call_interpreter(self):
        return await self.client.interpret_turn(
            message="Hello",
            state={"fields": {}, "pending_field": None},
            history=[],
            field_config=self.fields,
            company_knowledge="# About the company\nSample",
        )

    async def test_retries_without_json_mode_when_model_rejects_it(self):
        create = AsyncMock(
            side_effect=[
                UnsupportedJsonMode("response_format json_object is unsupported"),
                self.response(self.valid_json()),
            ]
        )
        self.client.client.chat.completions.create = create

        result = await self.call_interpreter()

        self.assertEqual(result["intent"], "general")
        self.assertIn("response_format", create.call_args_list[0].kwargs)
        self.assertNotIn("response_format", create.call_args_list[1].kwargs)

    async def test_retries_invalid_json_with_correction_instruction(self):
        create = AsyncMock(
            side_effect=[
                self.response("not JSON"),
                self.response(self.valid_json()),
            ]
        )
        self.client.client.chat.completions.create = create

        result = await self.call_interpreter()

        self.assertEqual(result["recommended_action"], "clarify_intent")
        retry_messages = create.call_args_list[1].kwargs["messages"]
        self.assertIn("previous response was invalid", retry_messages[-1]["content"])


if __name__ == "__main__":
    unittest.main()
