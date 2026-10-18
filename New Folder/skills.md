[10/8/2026 11:43 AM] Artur Ayrapetyan (BB USA): You are a senior Python AI engineer.

Build a complete Telegram AI agent in the current folder.

The bot is a company information + HR application agent.

IMPORTANT:
This must be an AGENTIC conversational workflow, not a deterministic
question-1 → question-2 → question-3 chatbot.

Use:
- Python
- python-telegram-bot
- long polling
- OpenRouter API
- openai package (OpenRouter exposes an OpenAI-compatible API; configure
  the official `openai` SDK's AsyncOpenAI client with
  base_url="https://openrouter.ai/api/v1" and api_key=OPENROUTER_API_KEY
  — there is no separate "openrouter" package)
- python-dotenv
- local JSON files for persistence
- NO database
- NO LangGraph
- NO web framework
- NO webhook
- NO Docker

The project should be simple enough for beginners to understand, but architecturally clean.

==================================================
1. ENVIRONMENT
==================================================

Read these variables from .env:

TELEGRAM_BOT_TOKEN=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=

Provide .env.example.

Never hardcode secrets.

Add .env to .gitignore.

==================================================
2. MAIN BEHAVIOR
==================================================

The Telegram bot has two main capabilities:

A. COMPANY INFORMATION CHAT

Users can ask natural-language questions about the company.

The bot must answer ONLY using information from:

company_knowledge.md

If the answer cannot be found in company_knowledge.md, clearly say that
the information is not available.

Never invent company information.

Example:

User:
"Do you hire remote workers?"

Bot:
Answer using company_knowledge.md if the information exists.

Otherwise:
"I don't have confirmed information about that."

==================================================
B. HR APPLICATION AGENT
==================================================

The bot must recognize when the user wants to apply for a job.

Examples:

"I want to apply"
"I am looking for a job"
"Are you hiring?"
"I would like to work for you"

When this intent is detected, start an HR application conversation.

There are exactly 7 REQUIRED INFORMATION FIELDS:

1. full_name
2. location
3. experience
4. position
5. availability
6. work_authorization
7. phone

IMPORTANT:

These are required business fields, NOT seven fixed conversational turns.

The conversation can take 7, 10, 15 or more messages.

The application is completed ONLY when all 7 required fields contain
sufficient information.

==================================================
3. AGENTIC BEHAVIOR
==================================================

The bot must behave naturally.

Do NOT simply ask the seven questions sequentially.

For every incoming user message during an HR application, the AI should
analyze:

- Did the user answer the pending question?
- Is the answer sufficient?
- Is the answer ambiguous or incomplete?
- Did the user provide information for OTHER required fields?
- Did the user ask a side question?
- Did the user change topic?
- Is a follow-up question required?
- Which required fields are still missing?
- What is the best next conversational action?

For example:

Bot:
"Tell me about your work experience."

User:
"I worked in trucking."

This may be insufficient.

The agent should naturally follow up:

"What role did you have in trucking, and approximately how long did you
work in that role?"

Do not mark experience complete until enough meaningful information was
provided.

Another example:

Bot:
"What city are you located in?"

User:
"I'm in Chicago, and I can start in November."

The agent should extract BOTH:

location = Chicago
availability = November

Then it should NOT ask availability again later.

==================================================
4. SIDE QUESTIONS
==================================================

The user may interrupt the HR interview with a company question.

Example:

Bot:
"Do you have authorization to work in the US?"

User:
"Do you offer remote positions?"

The bot must:

1. Recognize that this is NOT an answer to work_authorization.
2. Answer
[10/8/2026 11:43 AM] Artur Ayrapetyan (BB USA): the user's company question using company_knowledge.md.
3. Keep work_authorization as missing.
4. Naturally return to the interview.

Example:

"Yes, some positions are remote.

Returning to your application: do you currently have authorization to
work in the US?"

The agent should remember where the conversation was.

==================================================
5. STRUCTURED AI DECISION
==================================================

Do NOT let the model directly control the application state with arbitrary
free text.

For every user turn, first use the model (via OpenRouter) as a TURN
INTERPRETER.

It should return structured JSON similar to:

{
  "intent": "company_question | hr_application | general | unknown",

  "extracted_fields": {
    "full_name": null,
    "location": null,
    "experience": null,
    "position": null,
    "availability": null,
    "work_authorization": null,
    "phone": null
  },

  "answers_pending_field": true,

  "answer_quality": "sufficient | insufficient | not_answered",

  "side_question": null,

  "recommended_action":
    "answer_company_question |
     start_hr_application |
     ask_next_field |
     ask_followup |
     answer_side_question_then_continue |
     clarify_intent |
     complete_application",

  "followup_goal": null
}

Request JSON output via the chat completions call (e.g.
response_format={"type": "json_object"}) if the chosen OpenRouter model
supports it; not every model routed through OpenRouter honors structured
output equally well, so validate defensively regardless.

Validate this result in Python before modifying state.

==================================================
6. PYTHON CONTROLLER
==================================================

Python is the source of truth for business rules.

The model may RECOMMEND actions.

Python decides whether the action is allowed.

In particular:

The model must NEVER be allowed to complete the HR application unless all
7 required fields are populated and valid.

Python must calculate missing fields itself.

Pseudo logic:

missing_fields = all required fields where value is missing

if missing_fields:
    application cannot be completed

if no missing_fields:
    application may be completed

The LLM handles:
- natural language understanding
- extracting information
- determining whether answers are sufficient
- generating follow-up questions
- natural conversation

Python handles:
- required fields
- application state
- persistence
- completion rules
- validation
- allowed actions

This is bounded/constrained agency.

==================================================
7. HR FIELD CONFIGURATION
==================================================

Do not hardcode conversational wording for the seven questions.

Create:

config/hr_fields.json

Each field should contain something like:

{
  "field": "experience",
  "required": true,
  "goal": "Understand the candidate's relevant work experience, role and approximate duration",
  "validation": "Must contain meaningful information about previous work, ideally role/domain and approximate duration"
}

The model should generate natural questions based on the goal.

Therefore the same field may result in different questions depending on
the conversation.

Example:

First:
"Tell me a little about your professional experience."

Follow-up:
"What role did you have?"

Another follow-up:
"Approximately how many years did you work in that role?"

==================================================
8. STATE
==================================================

Maintain state per Telegram chat_id.

State should contain approximately:

{
  "chat_id": "...",
  "mode": "general_chat | hr_application | completed",

  "fields": {
    "full_name": null,
    "location": null,
    "experience": null,
    "position": null,
    "availability": null,
    "work_authorization": null,
    "phone": null
  },

  "pending_field": null,

  "conversation": [],

  "completed": false
}

Do NOT use current_question=1/2/3 as the primary state mechanism.

The primary mechanism should be:

WHAT
[10/8/2026 11:43 AM] Artur Ayrapetyan (BB USA): INFORMATION IS ALREADY KNOWN?
WHAT REQUIRED INFORMATION IS STILL MISSING?

==================================================
9. PERSISTENCE
==================================================

No database.

Use:

data/sessions.json
data/applications.json

sessions.json:
stores active conversation state by Telegram chat_id.

applications.json:
stores completed HR applications.

When an application becomes complete:

1. Add the completed application to applications.json.
2. Mark session completed.
3. Send a confirmation message.

Example:

"Thank you! I have collected all the information required for your
application. Your application has been recorded."

Use safe JSON persistence.

Avoid corrupting JSON if the program stops while writing:
write to a temporary file and atomically replace the original.

A simple asyncio.Lock for file access is enough.

==================================================
10. CONVERSATION HISTORY
==================================================

Keep recent conversation history in the session.

Do not send an unlimited conversation to the model.

Keep a reasonable recent history, for example the last 15-20 messages,
plus the structured state.

The structured fields are the primary long-term memory.

==================================================
11. RESPONSE GENERATION
==================================================

Separate:

TURN INTERPRETATION

from:

RESPONSE GENERATION

The interpreter should produce structured JSON.

Then Python determines the allowed action.

Then the model (via OpenRouter) may generate the final natural Telegram
response using:

- selected action
- conversation context
- pending field
- missing fields
- company knowledge when relevant
- follow-up goal

Do not let response generation alter business state.

==================================================
12. COMPANY KNOWLEDGE
==================================================

Create:

company_knowledge.md

Include placeholder example sections:

# About the company

# Services

# Locations

# Careers

# Working conditions

# Contact information

Clearly mark the content as EXAMPLE CONTENT that I should replace later,
but keep that disclaimer addressed to the human reader only (e.g. a single
comment at the top of the file). Do not repeat words like "placeholder"
or "example" inline next to each fact — the model reads this file as its
only source of company facts, and inline disclaimers make it treat real-
looking example data as unconfirmed and refuse to answer with it.

When answering company questions:

- use only this file
- do not use general model knowledge
- do not hallucinate
- if information is absent, explicitly say so

For this workshop, loading the entire small Markdown file into context is
fine.

Do NOT implement embeddings, vector databases or RAG infrastructure.

Keep it simple.

==================================================
13. TELEGRAM
==================================================

Use python-telegram-bot.

Use long polling.

Commands:

/start
- explain what the bot can do

/apply
- explicitly start a new HR application

/status
- show which application fields are complete and which are still missing

/cancel
- cancel/reset current HR application

/reset
- completely reset the user's session

Normal text messages should go through the agentic conversation logic.

==================================================
14. PROJECT STRUCTURE
==================================================

Prefer a simple structure similar to:

company-agent/
│
├── app.py
├── agent.py
├── llm.py
├── storage.py
├── config.py
│
├── config/
│   └── hr_fields.json
│
├── data/
│   ├── sessions.json
│   └── applications.json
│
├── company_knowledge.md
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md

Keep it understandable.

Do not introduce unnecessary abstractions.

==================================================
15. LOGGING
==================================================

Add basic Python logging.

Log:

- bot startup
- chat_id
- detected intent
- extracted fields
- selected
[10/8/2026 11:43 AM] Artur Ayrapetyan (BB USA): action
- missing fields
- application completion
- API errors

Never log API keys.

==================================================
16. ERROR HANDLING
==================================================

Give every OpenRouter call a request timeout (e.g. 25 seconds). Without
one, a stalled request hangs the Telegram handler forever and the user
gets no reply at all instead of a friendly error message.

If the model call fails (including a timeout):

Send a friendly Telegram message such as:

"Sorry, I had trouble processing that message. Please try again."

Do not destroy the user's session.

If JSON returned from the model cannot be parsed:

retry once.

If it still fails:
handle gracefully.

==================================================
17. REQUIREMENTS
==================================================

Create requirements.txt with only the packages actually needed.

Expected packages include approximately:

python-telegram-bot
openai
python-dotenv

Avoid unnecessary frameworks.

==================================================
18. README
==================================================

Write a beginner-friendly README.

Include:

1. Create virtual environment
2. Install requirements
3. Copy .env.example to .env
4. Add TELEGRAM_BOT_TOKEN
5. Add OPENROUTER_API_KEY (from https://openrouter.ai/keys)
6. Set OPENROUTER_MODEL to a model slug available on OpenRouter (e.g.
   "openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet",
   "google/gemini-2.0-flash-001" — check https://openrouter.ai/models for
   current options and pricing)
7. Run:

python app.py

Explain that the bot uses long polling, so it can run locally without a
public server.

Also explain:

.env must NEVER be committed to GitHub.

==================================================
19. IMPORTANT DESIGN REQUIREMENTS
==================================================

DO NOT create a simple deterministic questionnaire.

DO NOT rely entirely on a giant system prompt.

DO NOT allow the LLM to decide whether mandatory business requirements
can be skipped.

DO NOT use a database.

DO NOT use LangGraph.

DO NOT use n8n.

DO NOT use Flask/FastAPI.

DO NOT create a web UI.

The key architecture is:

Telegram
    ↓
Python
    ↓
Turn Interpreter (structured output via OpenRouter)
    ↓
Update extracted information
    ↓
Python Business Controller
    ↓
Choose allowed next action
    ↓
Conversation Generator (natural text via OpenRouter)
    ↓
Telegram

State:
local JSON

Required HR information:
controlled by Python/config

Natural conversational behavior:
controlled by the model (via OpenRouter)

==================================================
20. TEST SCENARIOS
==================================================

After implementing, manually reason through these scenarios and make sure
the architecture handles all of them.

SCENARIO A

User:
"I want to apply for a job."

Bot:
Starts application.

Bot asks about experience.

User:
"I worked in trucking."

Bot:
Asks a meaningful follow-up instead of blindly moving on.

--------------------------------------------------

SCENARIO B

Bot asks location.

User:
"Chicago. I can start in November."

System extracts:

location = Chicago
availability = November

It should not ask availability later.

--------------------------------------------------

SCENARIO C

Bot asks about experience.

User:
"Do you offer remote work?"

The system:

- recognizes this as a side question
- answers using company_knowledge.md
- does NOT mark experience complete
- naturally returns to asking about experience

--------------------------------------------------

SCENARIO D

User says at the beginning:

"My name is John Smith, I'm in Chicago, I've been a dispatcher for 4
years, and I want to apply for a dispatcher position."

System should extract:

full_name
location
experience
position

and only ask for the remaining fields.

--------------------------------------------------

SCENARIO E

The model recommends:

complete_application

but phone is missing.

Python must reject that action and continue collecting
[10/8/2026 11:43 AM] Artur Ayrapetyan (BB USA): information.

--------------------------------------------------

SCENARIO F

The user provides an unclear answer.

Bot should generate a contextual follow-up rather than repeating the same
question word-for-word.

==================================================
21. IMPLEMENTATION PROCESS
==================================================

Before writing code:

1. Briefly show me the architecture you plan to implement.
2. Show me the proposed file structure.
3. Then implement the complete project.
4. Run syntax/import checks.
5. Fix errors you encounter.
6. Finally explain:
   - how the agent loop works
   - where business rules live
   - where AI decisions happen
   - how state is persisted
   - how I can change the seven HR fields later

Do not stop after scaffolding.
Build a runnable version.