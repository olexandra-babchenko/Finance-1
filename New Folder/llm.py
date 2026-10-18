"""OpenRouter calls for structured turn interpretation and natural replies."""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

INTENTS = {"company_question", "hr_application", "general", "unknown"}
QUALITIES = {"sufficient", "insufficient", "not_answered"}
ACTIONS = {
    "answer_company_question",
    "start_hr_application",
    "ask_next_field",
    "ask_followup",
    "answer_side_question_then_continue",
    "clarify_intent",
    "complete_application",
}

INTERPRETER_PROMPT = """You interpret each incoming message for a Telegram company and HR agent.
Return exactly one JSON object with these keys:
{
  "intent": "company_question | hr_application | general | unknown",
  "extracted_fields": {"full_name": null, "location": null, "experience": null,
    "position": null, "availability": null, "work_authorization": null, "phone": null},
  "answers_pending_field": true,
  "answer_quality": "sufficient | insufficient | not_answered",
  "side_question": null,
  "recommended_action": "answer_company_question | start_hr_application | ask_next_field | ask_followup | answer_side_question_then_continue | clarify_intent | complete_application",
  "followup_goal": null
}
Use only these required field names. Extract only information the user actually stated; use null otherwise. Mark an answer insufficient when it lacks the meaningful detail requested by the field goal. A short company question during an application is a side_question, not an answer to the pending field. Never decide that the application is complete; Python validates all seven fields. The company knowledge below is the only source for classifying company-topic questions, not a license to invent answers."""

RESPONSE_PROMPT = """You are a helpful, natural Telegram assistant for a company and its job applicants.
Follow the selected Python action and do not change application state or business rules.
For company questions, answer only from the supplied company knowledge. If the answer is absent, say: \"I don't have confirmed information about that.\" Never use outside knowledge or invent company facts.
For applications, be conversational. Ask one focused question or follow-up at a time, based on the field goal and conversation. A user may provide several fields in one message, so never ask for information Python already has. If answering a side question, answer it from company knowledge and then return naturally to the pending application field.
Keep replies concise and suitable for Telegram. Return plain text only."""


class LLMError(RuntimeError):
    """Raised when OpenRouter cannot provide a usable response."""


class OpenRouterClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=25.0,
            max_retries=0,
        )

    async def interpret_turn(
        self,
        *,
        message: str,
        state: dict[str, Any],
        history: list[dict[str, str]],
        field_config: list[dict[str, Any]],
        company_knowledge: str,
    ) -> dict[str, Any]:
        context = {
            "incoming_message": message,
            "pending_field": state.get("pending_field"),
            "known_fields": state.get("fields", {}),
            "field_goals": field_config,
            "recent_conversation": history[-18:],
            "company_knowledge": company_knowledge,
        }
        messages = [
            {"role": "system", "content": INTERPRETER_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]

        last_error: Exception | None = None
        response_format: dict[str, str] | None = {"type": "json_object"}
        for attempt in range(2):
            try:
                try:
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        **({"response_format": response_format} if response_format else {}),
                    )
                except Exception as exc:
                    if response_format is None or not self._rejects_json_mode(exc):
                        raise
                    logger.warning("Selected model rejected JSON mode; retrying with JSON instructions")
                    response_format = None
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                    )
                content = response.choices[0].message.content or ""
                parsed = self._parse_interpretation(content)
                return parsed
            except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == 0:
                    logger.warning("Interpreter returned invalid JSON; retrying once")
                    messages = [
                        *messages,
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": "Your previous response was invalid. Return one corrected JSON object using the required schema, with no markdown or extra text.",
                        },
                    ]

        raise LLMError("The interpreter returned an invalid response twice") from last_error

    @staticmethod
    def _rejects_json_mode(error: Exception) -> bool:
        message = str(error).casefold()
        return getattr(error, "status_code", None) == 400 and any(
            marker in message for marker in ("response_format", "json_object", "json mode")
        )

    async def generate_response(
        self,
        *,
        action: str,
        message: str,
        state: dict[str, Any],
        history: list[dict[str, str]],
        field_config: list[dict[str, Any]],
        company_knowledge: str,
        followup_goal: str | None,
    ) -> str:
        context = {
            "selected_action": action,
            "incoming_message": message,
            "application_mode": state.get("mode"),
            "pending_field": state.get("pending_field"),
            "known_fields": state.get("fields", {}),
            "missing_fields": [
                field["field"]
                for field in field_config
                if not state.get("fields", {}).get(field["field"])
            ],
            "followup_goal": followup_goal,
            "company_knowledge": company_knowledge,
        }
        messages = [
            {"role": "system", "content": RESPONSE_PROMPT},
            *history[-18:],
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
        except Exception as exc:
            raise LLMError("Could not generate a response") from exc

        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise LLMError("The model returned an empty response")
        return text[:4000]

    @staticmethod
    def _parse_interpretation(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError("Interpreter response must be a JSON object")

        fields = result.get("extracted_fields")
        if not isinstance(fields, dict):
            raise ValueError("extracted_fields must be an object")
        normalized_fields: dict[str, str | None] = {}
        allowed_fields = {
            "full_name", "location", "experience", "position",
            "availability", "work_authorization", "phone",
        }
        for name in allowed_fields:
            value = fields.get(name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{name} must be a string or null")
            normalized_fields[name] = value.strip()[:500] if value else None

        intent = result.get("intent")
        quality = result.get("answer_quality")
        action = result.get("recommended_action")
        if intent not in INTENTS or quality not in QUALITIES or action not in ACTIONS:
            raise ValueError("Interpreter returned an unsupported enum value")
        if not isinstance(result.get("answers_pending_field"), bool):
            raise ValueError("answers_pending_field must be a boolean")

        side_question = result.get("side_question")
        followup_goal = result.get("followup_goal")
        if side_question is not None and not isinstance(side_question, str):
            raise ValueError("side_question must be a string or null")
        if followup_goal is not None and not isinstance(followup_goal, str):
            raise ValueError("followup_goal must be a string or null")

        return {
            "intent": intent,
            "extracted_fields": normalized_fields,
            "answers_pending_field": result["answers_pending_field"],
            "answer_quality": quality,
            "side_question": side_question[:500] if side_question else None,
            "recommended_action": action,
            "followup_goal": followup_goal[:500] if followup_goal else None,
        }
