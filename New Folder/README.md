# NomadGH Telegram AI Agent

A Telegram bot for company information and job applications. It uses OpenRouter for conversational language understanding, Python for application rules, and local JSON files for session and application data.

## Requirements

- Python 3.10 or newer
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An OpenRouter API key from [openrouter.ai/keys](https://openrouter.ai/keys)
- A model slug available on [OpenRouter Models](https://openrouter.ai/models)

## Setup

1. Open a terminal in this folder.
2. Create and activate a virtual environment.

   Windows PowerShell:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   macOS or Linux:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`.

   Windows PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

   macOS or Linux:

   ```bash
   cp .env.example .env
   ```

5. Edit `.env` and set `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, and `OPENROUTER_MODEL`. Use a model slug currently listed by OpenRouter; the provided example uses `openrouter/free`.
6. Review `company_knowledge.md` and replace its clearly marked sample company details, contact information, and vacancies with verified information.
7. Start the bot:

   ```bash
   python app.py
   ```

The bot uses Telegram long polling, so it can run locally without a public server. Keep the process running while you want the bot online.

## Telegram commands

- `/start` shows the bot's capabilities.
- `/apply` starts a job application.
- `/status` shows completed and missing application fields.
- `/cancel` removes the current application session.
- `/reset` clears the session.

## Project behavior

- `company_knowledge.md` is the bot's only source for company facts. Add verified facts there; the bot should say when information is unavailable.
- `config/hr_fields.json` defines the required HR fields and the goals used to ask natural follow-up questions.
- `agent.py` validates fields and owns application completion rules. The model cannot complete an application on its own.
- `llm.py` performs structured turn interpretation and generates conversational replies through OpenRouter.
- `storage.py` stores sessions in `data/sessions.json` and completed applications in `data/applications.json`, using atomic file replacement.

The bot needs all seven required fields before it records an application: full name, location, experience, position, availability, work authorization, and phone. Edit `config/hr_fields.json` to change field goals or required status. If you rename a field, update the matching field names and validation in `agent.py` and `llm.py` as well.

## Security and privacy

Never commit `.env` or share its values. `.gitignore` excludes `.env` and local JSON data. Completed applications contain personal information, so restrict access to the machine and files where the bot runs, and handle or delete application records according to your organization's retention policy.
