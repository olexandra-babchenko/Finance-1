"""Python-owned application rules around the conversational model."""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)
COMPLETION_MESSAGE = (
    "Thank you! I have collected all the information required for your "
    "application. Your application has been recorded."
)


class Store(Protocol):
    async def get_session(self, chat_id: str) -> dict[str, Any] | None: ...
    async def save_session(self, chat_id: str, state: dict[str, Any]) -> None: ...
    async def save_application(self, application: dict[str, Any]) -> None: ...


class LanguageModel(Protocol):
    async def interpret_turn(self, **kwargs: Any) -> dict[str, Any]: ...
    async def generate_response(self, **kwargs: Any) -> str: ...


def new_state(chat_id: str, mode: str = "general_chat") -> dict[str, Any]:
    return {
        "chat_id": chat_id,
        "mode": mode,
        "fields": {},
        "pending_field": None,
        "conversation": [],
        "completed": False,
    }


def _field_is_valid(name: str, value: str) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return False
    if name == "full_name":
        return len(cleaned.split()) >= 2
    if name == "location":
        return len(cleaned) >= 2
    if name == "experience":
        has_duration = bool(
            re.search(
                r"\b(?:\d+\+?\s*(?:years?|yrs?|months?|mos?)|"
                r"several years|a few years|many years)\b",
                cleaned,
                re.IGNORECASE,
            )
        )
        return len(cleaned) >= 15 and has_duration
    if name == "position":
        return len(cleaned) >= 3
    if name == "availability":
        return len(cleaned) >= 3
    if name == "work_authorization":
        return bool(
            re.search(
                r"\b(?:yes|no|authorized|authorization|eligible|ineligible|"
                r"citizen|permanent resident|green card|work permit|"
                r"can work|cannot work|need sponsorship|require sponsorship)\b",
                cleaned,
                re.IGNORECASE,
            )
        )
    if name == "phone":
        digits = re.sub(r"\D", "", cleaned)
        return 7 <= len(digits) <= 15
    return False


class Agent:
    def __init__(
        self,
        *,
        llm: LanguageModel,
        store: Store,
        field_config: list[dict[str, Any]],
        company_knowledge: str,
    ) -> None:
        self.llm = llm
        self.store = store
        self.field_config = field_config
        self.company_knowledge = company_knowledge
        self.required_fields = [
            field["field"] for field in field_config if field.get("required", True)
        ]

    def _missing(self, state: dict[str, Any]) -> list[str]:
        values = state.get("fields", {})
        return [
            name for name in self.required_fields
            if not _field_is_valid(name, values.get(name, ""))
        ]

    def status_text(self, state: dict[str, Any]) -> str:
        fields = state.get("fields", {})
        lines = ["Application status:"]
        for name in self.required_fields:
            label = name.replace("_", " ").title()
            marker = "Complete" if _field_is_valid(name, fields.get(name, "")) else "Missing"
            lines.append(f"{marker}: {label}")
        if state.get("completed"):
            lines.append("Application submitted.")
        return "\n".join(lines)

    async def start_application(self, chat_id: str) -> str:
        state = new_state(chat_id, mode="hr_application")
        state["pending_field"] = self._missing(state)[0]
        await self.store.save_session(chat_id, state)
        return await self._generate_and_save(
            chat_id=chat_id,
            message="/apply",
            state=state,
            action="start_hr_application",
            followup_goal=self._goal_for(state["pending_field"]),
        )

    async def handle_text(self, chat_id: str, message: str) -> str:
        state = await self.store.get_session(chat_id) or new_state(chat_id)
        history = state.setdefault("conversation", [])
        old_mode = state.get("mode", "general_chat")
        interpretation = await self.llm.interpret_turn(
            message=message,
            state=state,
            history=history,
            field_config=self.field_config,
            company_knowledge=self.company_knowledge,
        )
        intent = interpretation["intent"]
        if old_mode != "hr_application" and intent == "hr_application":
            state = new_state(chat_id, mode="hr_application")
            history = state["conversation"]
        active_application = state.get("mode") == "hr_application"

        logger.info(
            "chat_id=%s intent=%s extracted_fields=%s",
            chat_id,
            intent,
            [name for name, value in interpretation["extracted_fields"].items() if value],
        )

        if active_application:
            prior_pending = state.get("pending_field")
            fields = state.setdefault("fields", {})
            for name, value in interpretation["extracted_fields"].items():
                if name not in self.required_fields or not value:
                    continue
                if (
                    name == prior_pending
                    and interpretation["answers_pending_field"]
                    and interpretation["answer_quality"] == "insufficient"
                ):
                    continue
                if _field_is_valid(name, value):
                    fields[name] = value

            missing = self._missing(state)
            side_question = interpretation.get("side_question")
            is_company_question = intent == "company_question"
            if not missing:
                action = "complete_application"
            elif side_question or is_company_question:
                action = "answer_side_question_then_continue"
                if prior_pending in missing:
                    state["pending_field"] = prior_pending
                else:
                    state["pending_field"] = missing[0]
            elif prior_pending in missing:
                state["pending_field"] = prior_pending
                action = "ask_followup"
            else:
                state["pending_field"] = missing[0]
                action = "start_hr_application" if old_mode != "hr_application" else "ask_next_field"

            if action == "complete_application":
                completed_at = datetime.now(timezone.utc).isoformat()
                application = {
                    "chat_id": chat_id,
                    "fields": {name: fields[name] for name in self.required_fields},
                    "completed_at": completed_at,
                }
                await self.store.save_application(application)
                state["mode"] = "completed"
                state["completed"] = True
                state["pending_field"] = None
                await self._append_exchange(state, message, COMPLETION_MESSAGE)
                await self.store.save_session(chat_id, state)
                logger.info("chat_id=%s application completed", chat_id)
                return COMPLETION_MESSAGE

            missing = self._missing(state)
            logger.info(
                "chat_id=%s action=%s missing_fields=%s",
                chat_id,
                action,
                missing,
            )
            await self.store.save_session(chat_id, state)
            return await self._generate_and_save(
                chat_id=chat_id,
                message=message,
                state=state,
                action=action,
                followup_goal=interpretation.get("followup_goal") or self._goal_for(state.get("pending_field")),
            )

        if intent == "company_question":
            action = "answer_company_question"
        elif intent == "hr_application":
            # A defensive fallback; a new application normally enters the branch above.
            return await self.start_application(chat_id)
        else:
            action = "clarify_intent"

        logger.info("chat_id=%s action=%s missing_fields=[]", chat_id, action)
        return await self._generate_and_save(
            chat_id=chat_id,
            message=message,
            state=state,
            action=action,
            followup_goal=None,
        )

    async def _generate_and_save(
        self,
        *,
        chat_id: str,
        message: str,
        state: dict[str, Any],
        action: str,
        followup_goal: str | None,
    ) -> str:
        reply = await self.llm.generate_response(
            action=action,
            message=message,
            state=state,
            history=state.get("conversation", []),
            field_config=self.field_config,
            company_knowledge=self.company_knowledge,
            followup_goal=followup_goal,
        )
        await self._append_exchange(state, message, reply)
        await self.store.save_session(chat_id, state)
        return reply

    @staticmethod
    async def _append_exchange(state: dict[str, Any], message: str, reply: str) -> None:
        conversation = state.setdefault("conversation", [])
        conversation.extend(
            [
                {"role": "user", "content": message[:2000]},
                {"role": "assistant", "content": reply[:4000]},
            ]
        )
        state["conversation"] = conversation[-20:]

    def _goal_for(self, name: str | None) -> str | None:
        if not name:
            return None
        for field in self.field_config:
            if field["field"] == name:
                return field.get("goal")
        return None
