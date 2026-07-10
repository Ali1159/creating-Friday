#!/usr/bin/env python3
"""Friday: a Jarvis-style command line AI assistant."""

from __future__ import annotations

import ast
import json
import logging
import os
import shlex
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


def _safe_eval_math(expression: str) -> float | int:
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Constant,
    )
    tree = ast.parse(expression, mode="eval")
    if any(not isinstance(node, allowed_nodes) for node in ast.walk(tree)):
        raise ValueError("Only arithmetic expressions are allowed.")
    result = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, {})
    if not isinstance(result, (int, float)):
        raise ValueError("Expression did not produce a numeric result.")
    return result


def _parse_duration(token: str) -> int:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if len(token) < 2 or token[-1].lower() not in units:
        raise ValueError("Duration must look like 10s, 5m, 2h, 1d.")
    value = int(token[:-1])
    if value <= 0:
        raise ValueError("Duration must be greater than zero.")
    return value * units[token[-1].lower()]


class JsonStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = {
            "notes": [],
            "todos": [],
            "reminders": [],
            "alarms": [],
            "preferences": {},
            "history": [],
        }
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.save()
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (json.JSONDecodeError, OSError):
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)


@dataclass
class Plugin:
    name: str
    description: str
    category: str
    requires_permission: bool
    handler: Callable[[list[str]], str]


class Friday:
    def __init__(
        self,
        root_dir: Path | None = None,
        input_func: Callable[[str], str] = input,
    ) -> None:
        self.root_dir = root_dir or Path.cwd()
        self.input_func = input_func
        self.config = self._load_config(self.root_dir)
        self.name = self.config.get("name", "Friday")
        data_file = Path(self.config.get("data_file", "friday_data.json"))
        log_file = Path(self.config.get("log_file", "friday.log"))
        self.allow_unsafe = bool(self.config.get("allow_unsafe", False))
        self.llm_enabled = bool(self.config.get("llm_enabled", False))
        self.voice_enabled = bool(self.config.get("voice_enabled", False))
        self.store = JsonStore(self.root_dir / data_file)
        self._should_exit = False
        self.logger = self._build_logger(self.root_dir / log_file)
        self.plugins: dict[str, Plugin] = {}
        self._register_builtin_plugins()
        self._commands = {
            "help": self._cmd_help,
            "time": self._cmd_time,
            "date": self._cmd_date,
            "status": self._cmd_status,
            "calc": self._cmd_calc,
            "note": self._cmd_note,
            "todo": self._cmd_todo,
            "remind": self._cmd_remind,
            "alarm": self._cmd_alarm,
            "due": self._cmd_due,
            "pref": self._cmd_pref,
            "plugin": self._cmd_plugin,
            "voice": self._cmd_voice,
            "llm": self._cmd_llm,
            "history": self._cmd_history,
            "exit": self._cmd_exit,
            "quit": self._cmd_exit,
        }

    def _build_logger(self, path: Path) -> logging.Logger:
        logger = logging.getLogger("friday")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.FileHandler(path, encoding="utf-8")
            formatter = logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    def _load_config(self, root_dir: Path) -> dict[str, Any]:
        config: dict[str, Any] = {}
        env_values = self._load_env(root_dir / ".env")
        config.update(env_values)

        config_file = root_dir / "config.toml"
        if config_file.exists() and tomllib is not None:
            with config_file.open("rb") as f:
                loaded = tomllib.load(f)
            if isinstance(loaded, dict):
                for key, value in loaded.items():
                    if not isinstance(value, dict):
                        config[key] = value
                if isinstance(loaded.get("default"), dict):
                    config.update(loaded["default"])
                profile_name = os.getenv("FRIDAY_PROFILE", config.get("profile", "default"))
                profiles = loaded.get("profiles", {})
                if isinstance(profiles, dict) and isinstance(profiles.get(profile_name), dict):
                    config.update(profiles[profile_name])

        config["allow_unsafe"] = str(config.get("allow_unsafe", "false")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        config["llm_enabled"] = str(config.get("llm_enabled", "false")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        config["voice_enabled"] = str(config.get("voice_enabled", "false")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return config

    @staticmethod
    def _load_env(path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        if not path.exists():
            return values
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip().lower()] = value.strip().strip("'\"")
        return values

    def _next_id(self, key: str) -> int:
        current = self.store.data.get(key, [])
        if not current:
            return 1
        return max(int(item.get("id", 0)) for item in current) + 1

    def _register_builtin_plugins(self) -> None:
        self.register_plugin(
            Plugin(
                name="echo",
                description="Echo text back.",
                category="safe",
                requires_permission=False,
                handler=lambda args: " ".join(args) if args else "Nothing to echo.",
            )
        )
        self.register_plugin(
            Plugin(
                name="list_files",
                description="List files in the repository root.",
                category="file",
                requires_permission=True,
                handler=self._plugin_list_files,
            )
        )
        self.register_plugin(
            Plugin(
                name="fetch_url",
                description="Fetch text content from a URL.",
                category="network",
                requires_permission=True,
                handler=self._plugin_fetch_url,
            )
        )

    def register_plugin(self, plugin: Plugin) -> None:
        self.plugins[plugin.name] = plugin

    def greet(self) -> str:
        return (
            f"{self.name} online. Type 'help' for commands. "
            "I support command routing, persistent tasks, plugins, and optional voice/LLM."
        )

    def respond(self, text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return "Awaiting your instruction."

        self.logger.info("USER %s", cleaned)
        self._record_history("user", cleaned)

        try:
            parts = shlex.split(cleaned)
        except ValueError as exc:
            return f"Could not parse command: {exc}"

        if parts:
            command = parts[0].lower()
            args = parts[1:]
            handler = self._commands.get(command)
            if handler is not None:
                response = handler(args)
                self._record_history("friday", response)
                self.logger.info("FRIDAY %s", response)
                return response

        lowered = cleaned.lower()
        if any(word in lowered for word in ("hello", "hi", "hey")):
            response = "Hello. Friday is at your service."
        elif "your name" in lowered:
            response = f"I am {self.name}, your personal AI assistant."
        else:
            response = self._fallback_response(cleaned)

        self._record_history("friday", response)
        self.logger.info("FRIDAY %s", response)
        return response

    def _record_history(self, role: str, text: str) -> None:
        self.store.data.setdefault("history", []).append(
            {"ts": datetime.now().isoformat(), "role": role, "text": text}
        )
        self.store.data["history"] = self.store.data["history"][-500:]
        self.store.save()

    def _fallback_response(self, prompt: str) -> str:
        if self.llm_enabled:
            llm = self._ask_llm(prompt)
            if llm:
                return llm
        return (
            "Command acknowledged. Try 'help' for available commands, "
            "or enable LLM with: llm on"
        )

    def _ask_llm(self, prompt: str) -> str | None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "LLM fallback is enabled, but OPENAI_API_KEY is not set."

        endpoint = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are Friday, a concise and helpful AI assistant."},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = json.loads(response.read().decode("utf-8"))
            choices = body.get("choices", [])
            if choices and "message" in choices[0]:
                return choices[0]["message"].get("content", "").strip() or None
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
            return "LLM service is currently unavailable."
        return None

    def _should_allow_action(self, action_name: str, category: str) -> bool:
        if self.allow_unsafe:
            return True
        answer = self.input_func(
            f"Permission required for {category} action '{action_name}'. Allow? (y/N): "
        )
        return answer.strip().lower() in {"y", "yes"}

    def check_due_notifications(self) -> list[str]:
        now = datetime.now()
        notifications = []
        for key in ("reminders", "alarms"):
            for item in self.store.data.get(key, []):
                if item.get("triggered"):
                    continue
                due_at = item.get("due_at")
                if not due_at:
                    continue
                try:
                    due_time = datetime.fromisoformat(due_at)
                except ValueError:
                    continue
                if due_time <= now:
                    item["triggered"] = True
                    label = "Reminder" if key == "reminders" else "Alarm"
                    notifications.append(f"{label}: {item.get('text', '(no text)')}")
        if notifications:
            self.store.save()
        return notifications

    def _cmd_help(self, _: list[str]) -> str:
        return dedent(
            """
            Available commands:
              - help
              - time / date / status
              - calc <expression>
              - note add <text> | note list
              - todo add <text> | todo list | todo done <id> | todo remove <id>
              - remind <duration> <text>      (e.g. remind 10m drink water)
              - alarm <HH:MM> <text>
              - due                            (list pending reminders/alarms)
              - pref set <key> <value> | pref get <key> | pref list
              - plugin list | plugin run <name> [args...]
              - voice on|off|say <text>|listen
              - llm on|off|status
              - history [count]
              - exit / quit
            """
        ).strip()

    @staticmethod
    def _cmd_time(_: list[str]) -> str:
        return f"Current time: {datetime.now().strftime('%H:%M:%S')}"

    @staticmethod
    def _cmd_date(_: list[str]) -> str:
        return f"Today's date: {datetime.now().strftime('%Y-%m-%d')}"

    @staticmethod
    def _cmd_status(_: list[str]) -> str:
        return "All systems operational."

    def _cmd_calc(self, args: list[str]) -> str:
        if not args:
            return "Usage: calc <expression>"
        expression = " ".join(args)
        try:
            result = _safe_eval_math(expression)
            return f"Result: {result}"
        except (ValueError, SyntaxError) as exc:
            return f"Calculation error: {exc}"

    def _cmd_note(self, args: list[str]) -> str:
        if not args:
            return "Usage: note add <text> | note list"
        action = args[0].lower()
        if action == "add" and len(args) > 1:
            text = " ".join(args[1:]).strip()
            self.store.data.setdefault("notes", []).append(
                {"id": self._next_id("notes"), "text": text, "created_at": datetime.now().isoformat()}
            )
            self.store.save()
            return "Note saved."
        if action == "list":
            notes = self.store.data.get("notes", [])
            if not notes:
                return "No notes saved."
            return "\n".join(f"{n['id']}. {n['text']}" for n in notes)
        return "Usage: note add <text> | note list"

    def _cmd_todo(self, args: list[str]) -> str:
        if not args:
            return "Usage: todo add/list/done/remove ..."
        action = args[0].lower()
        todos = self.store.data.setdefault("todos", [])
        if action == "add" and len(args) > 1:
            text = " ".join(args[1:]).strip()
            todos.append(
                {
                    "id": self._next_id("todos"),
                    "text": text,
                    "done": False,
                    "created_at": datetime.now().isoformat(),
                }
            )
            self.store.save()
            return "Todo added."
        if action == "list":
            if not todos:
                return "Todo list is empty."
            return "\n".join(
                f"{item['id']}. [{'x' if item.get('done') else ' '}] {item['text']}" for item in todos
            )
        if action in {"done", "remove"} and len(args) == 2:
            try:
                target_id = int(args[1])
            except ValueError:
                return "Todo id must be a number."
            for index, item in enumerate(todos):
                if int(item.get("id", -1)) != target_id:
                    continue
                if action == "done":
                    item["done"] = True
                    self.store.save()
                    return "Todo marked as done."
                todos.pop(index)
                self.store.save()
                return "Todo removed."
            return "Todo not found."
        return "Usage: todo add/list/done/remove ..."

    def _cmd_remind(self, args: list[str]) -> str:
        if len(args) < 2:
            return "Usage: remind <duration> <text>"
        try:
            seconds = _parse_duration(args[0])
        except (ValueError, TypeError) as exc:
            return f"Invalid duration: {exc}"
        text = " ".join(args[1:]).strip()
        due_at = datetime.now() + timedelta(seconds=seconds)
        self.store.data.setdefault("reminders", []).append(
            {
                "id": self._next_id("reminders"),
                "text": text,
                "due_at": due_at.isoformat(),
                "triggered": False,
            }
        )
        self.store.save()
        return f"Reminder set for {due_at.strftime('%Y-%m-%d %H:%M:%S')}."

    def _cmd_alarm(self, args: list[str]) -> str:
        if len(args) < 2:
            return "Usage: alarm <HH:MM> <text>"
        time_token = args[0]
        text = " ".join(args[1:]).strip()
        try:
            hour, minute = map(int, time_token.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except ValueError:
            return "Invalid time format. Use HH:MM."

        now = datetime.now()
        due_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due_at <= now:
            due_at += timedelta(days=1)

        self.store.data.setdefault("alarms", []).append(
            {
                "id": self._next_id("alarms"),
                "text": text,
                "due_at": due_at.isoformat(),
                "triggered": False,
            }
        )
        self.store.save()
        return f"Alarm set for {due_at.strftime('%Y-%m-%d %H:%M:%S')}."

    def _cmd_due(self, _: list[str]) -> str:
        lines = []
        for key, label in (("reminders", "Reminder"), ("alarms", "Alarm")):
            for item in self.store.data.get(key, []):
                status = "triggered" if item.get("triggered") else "pending"
                lines.append(
                    f"{label} {item.get('id')}: {item.get('text')} @ {item.get('due_at')} [{status}]"
                )
        return "\n".join(lines) if lines else "No reminders or alarms found."

    def _cmd_pref(self, args: list[str]) -> str:
        if not args:
            return "Usage: pref set/get/list ..."
        prefs = self.store.data.setdefault("preferences", {})
        action = args[0].lower()
        if action == "set" and len(args) >= 3:
            key = args[1]
            value = " ".join(args[2:])
            prefs[key] = value
            self.store.save()
            return f"Preference '{key}' saved."
        if action == "get" and len(args) == 2:
            key = args[1]
            return f"{key}={prefs.get(key, '(not set)')}"
        if action == "list":
            if not prefs:
                return "No preferences saved."
            return "\n".join(f"{k}={v}" for k, v in sorted(prefs.items()))
        return "Usage: pref set/get/list ..."

    def _cmd_plugin(self, args: list[str]) -> str:
        if not args:
            return "Usage: plugin list | plugin run <name> [args...]"
        action = args[0].lower()
        if action == "list":
            return "\n".join(
                f"{name}: {plugin.description}" for name, plugin in sorted(self.plugins.items())
            )
        if action == "run" and len(args) >= 2:
            name = args[1]
            plugin = self.plugins.get(name)
            if plugin is None:
                return f"Plugin '{name}' not found."
            if plugin.requires_permission and not self._should_allow_action(name, plugin.category):
                return "Action denied by safety policy."
            try:
                return plugin.handler(args[2:])
            except Exception as exc:  # pragma: no cover
                return f"Plugin error: {exc}"
        return "Usage: plugin list | plugin run <name> [args...]"

    def _plugin_list_files(self, _: list[str]) -> str:
        names = sorted(path.name for path in self.root_dir.iterdir())
        return "\n".join(names) if names else "(empty)"

    @staticmethod
    def _plugin_fetch_url(args: list[str]) -> str:
        if not args:
            return "Usage: plugin run fetch_url <url>"
        url = args[0]
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "Friday-AI/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                content = response.read(500).decode("utf-8", errors="replace")
            return f"Fetched {url}\n{content}"
        except urllib.error.URLError as exc:
            return f"Network error: {exc}"

    def _cmd_voice(self, args: list[str]) -> str:
        if not args:
            return "Usage: voice on|off|say <text>|listen"
        action = args[0].lower()
        if action == "on":
            self.voice_enabled = True
            return "Voice mode enabled."
        if action == "off":
            self.voice_enabled = False
            return "Voice mode disabled."
        if action == "say":
            if len(args) < 2:
                return "Usage: voice say <text>"
            text = " ".join(args[1:])
            try:
                import pyttsx3  # type: ignore

                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
                return "Spoken."
            except Exception:
                return f"(TTS unavailable) {text}"
        if action == "listen":
            try:
                import speech_recognition as sr  # type: ignore

                recognizer = sr.Recognizer()
                with sr.Microphone() as source:
                    audio = recognizer.listen(source, timeout=5)
                heard = recognizer.recognize_google(audio)
                return f"Heard: {heard}"
            except Exception:
                return "Speech recognition unavailable."
        return "Usage: voice on|off|say <text>|listen"

    def _cmd_llm(self, args: list[str]) -> str:
        if not args:
            return "Usage: llm on|off|status"
        action = args[0].lower()
        if action == "on":
            self.llm_enabled = True
            return "LLM fallback enabled."
        if action == "off":
            self.llm_enabled = False
            return "LLM fallback disabled."
        if action == "status":
            status = "enabled" if self.llm_enabled else "disabled"
            return f"LLM fallback is {status}."
        return "Usage: llm on|off|status"

    def _cmd_history(self, args: list[str]) -> str:
        count = 10
        if args:
            try:
                count = max(1, int(args[0]))
            except ValueError:
                return "History count must be a number."
        events = self.store.data.get("history", [])[-count:]
        if not events:
            return "No history available."
        return "\n".join(f"{e['ts']} {e['role']}: {e['text']}" for e in events)

    def _cmd_exit(self, _: list[str]) -> str:
        self._should_exit = True
        return f"Shutting down {self.name}. Goodbye."


def run() -> None:
    friday = Friday()
    print(friday.greet())
    while not friday._should_exit:
        for notification in friday.check_due_notifications():
            print(f"{friday.name}> {notification}")
        try:
            user_input = input("You> ")
        except EOFError:
            break
        reply = friday.respond(user_input)
        print(f"{friday.name}> {reply}")


if __name__ == "__main__":
    run()
