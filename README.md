# creating-Friday

Jarvis-style AI assistant named **Friday**.

## Run Friday

From the repository root:

```bash
python3 friday.py
```

## Core features

- Command router with arguments (`calc 5*8`, `remind 10m drink water`)
- Persistent memory in `friday_data.json` (notes, todos, reminders, alarms, prefs, history)
- Todo/reminder/alarm task features
- Plugin/tool system with safety confirmations
- Optional voice mode (`voice say`, `voice listen`)
- Optional LLM fallback mode (`llm on`)
- Logging and conversation history

## Commands

```text
help
time / date / status
calc <expression>
note add <text> | note list
todo add <text> | todo list | todo done <id> | todo remove <id>
remind <duration> <text>      # 10s, 5m, 2h, 1d
alarm <HH:MM> <text>
due
pref set <key> <value> | pref get <key> | pref list
plugin list | plugin run <name> [args...]
voice on|off|say <text>|listen
llm on|off|status
history [count]
exit / quit
```

## Optional configuration

You can create `/home/runner/work/creating-Friday/creating-Friday/config.toml`:

```toml
[default]
name = "Friday"
data_file = "friday_data.json"
log_file = "friday.log"
allow_unsafe = false
voice_enabled = false
llm_enabled = false
```

And optional `/home/runner/work/creating-Friday/creating-Friday/.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=https://api.openai.com/v1/chat/completions
OPENAI_MODEL=gpt-4o-mini
```

## Quick example

```text
Friday online. Type 'help' for commands...
You> remind 10m drink water
Friday> Reminder set for 2026-07-10 10:00:00.
You> todo add finish prototype
Friday> Todo added.
You> plugin run list_files
Permission required for file action 'list_files'. Allow? (y/N): y
Friday> README.md
friday.py
```

## Run tests

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```
