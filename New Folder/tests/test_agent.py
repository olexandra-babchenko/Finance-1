"""Focused tests for business rules independent of Telegram and OpenRouter."""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agent import Agent, new_state  # noqa: E402


class FakeStore:
    def __init__(self):
        self.sessions = {}
        self.applications = []

    async def get_session(self, chat_id):
        return self.sessions.get(chat_id)

    async def save_session(self, chat_id, state):
        self.sessions[chat_id] = state

    async def delete_session(self, chat_id):
        self.sessions.pop(chat_id, None)

    async def save_application(self, application):
        self.applications.append(application)


class FakeLLM:
    def __init__(self, interpretation):
        self.interpretation = interpretation
        self.last_action = None

    async def interpret_turn(self, **kwargs):
        return self.interpretation

    async def generate_response(self, **kwargs):
        self.last_action = kwargs["action"]
        return f"Action: {self.last_action}"


def interpretation(fields, *, intent="hr_application", side_question=None):
    return {
        "intent": intent,
        "extracted_fields": fields,
        "answers_pending_field": False,
        "answer_quality": "not_answered",
        "side_question": side_question,
        "recommended_action": "complete_application",
        "followup_goal": None,
    }


class AgentTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.field_config = json.loads(
            (PROJECT_ROOT / "config" / "hr_fields.json").read_text(encoding="utf-8")
        )
        cls.knowledge = (PROJECT_ROOT / "company_knowledge.md").read_text(encoding="utf-8")
        cls.field_names = [field["field"] for field in cls.field_config]

    def make_agent(self, result, store=None):
        store = store or FakeStore()
        llm = FakeLLM(result)
        agent = Agent(
            llm=llm,
            store=store,
            field_config=self.field_config,
            company_knowledge=self.knowledge,
        )
        return agent, store, llm

    async def test_missing_phone_blocks_model_completion_recommendation(self):
        fields = {
            "full_name": "John Smith",
            "location": "Chicago, IL",
            "experience": "Dispatcher for 4 years",
            "position": "Dispatcher",
            "availability": "Starting in November",
            "work_authorization": "Authorized to work in the US",
            "phone": None,
        }
        state = new_state("42", "hr_application")
        state["fields"] = {key: value for key, value in fields.items() if value}
        state["pending_field"] = "phone"
        store = FakeStore()
        await store.save_session("42", state)
        agent, _, llm = self.make_agent(interpretation(fields), store)

        reply = await agent.handle_text("42", "I want to apply")

        self.assertEqual(reply, "Action: ask_followup")
        self.assertEqual(llm.last_action, "ask_followup")
        self.assertEqual(store.applications, [])

    async def test_side_question_keeps_pending_field(self):
        fields = {name: None for name in self.field_names}
        state = new_state("43", "hr_application")
        state["pending_field"] = "experience"
        store = FakeStore()
        await store.save_session("43", state)
        agent, _, llm = self.make_agent(
            interpretation(fields, intent="company_question", side_question="Do you offer remote work?"),
            store,
        )

        reply = await agent.handle_text("43", "Do you offer remote work?")

        self.assertEqual(reply, "Action: answer_side_question_then_continue")
        self.assertEqual(store.sessions["43"]["pending_field"], "experience")
        self.assertIsNone(store.sessions["43"]["fields"].get("experience"))

    async def test_all_valid_fields_record_application(self):
        fields = {
            "full_name": "John Smith",
            "location": "Chicago, IL",
            "experience": "Dispatcher for 4 years",
            "position": "Dispatcher",
            "availability": "Starting in November",
            "work_authorization": "Authorized to work in the US",
            "phone": "+1 312 555 0199",
        }
        agent, store, _ = self.make_agent(interpretation(fields))

        reply = await agent.handle_text("44", "I want to apply")

        self.assertIn("application has been recorded", reply)
        self.assertEqual(len(store.applications), 1)
        self.assertTrue(store.sessions["44"]["completed"])
        self.assertEqual(store.applications[0]["fields"], fields)

    async def test_short_experience_does_not_fill_required_field(self):
        fields = {name: None for name in self.field_names}
        fields["experience"] = "I worked in trucking"
        agent, store, _ = self.make_agent(interpretation(fields))

        await agent.handle_text("45", "I want to apply")

        self.assertNotIn("experience", store.sessions["45"]["fields"])
        self.assertFalse(store.sessions["45"]["completed"])

    async def test_ambiguous_work_authorization_does_not_complete_field(self):
        fields = {
            "full_name": "John Smith",
            "location": "Chicago, IL",
            "experience": "Dispatcher for 4 years",
            "position": "Dispatcher",
            "availability": "Starting in November",
            "work_authorization": "Maybe",
            "phone": "+1 312 555 0199",
        }
        agent, store, _ = self.make_agent(interpretation(fields))

        await agent.handle_text("46", "I want to apply")

        self.assertNotIn("work_authorization", store.sessions["46"]["fields"])
        self.assertFalse(store.sessions["46"]["completed"])


if __name__ == "__main__":
    unittest.main()
