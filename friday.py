#!/usr/bin/env python3
"""Friday: a lightweight Jarvis-style command line assistant."""

from __future__ import annotations

from datetime import datetime
from textwrap import dedent


class Friday:
    def __init__(self) -> None:
        self.name = "Friday"
        self._commands = {
            "help": self._help,
            "time": self._time,
            "date": self._date,
            "status": self._status,
            "exit": self._exit_text,
            "quit": self._exit_text,
        }

    def greet(self) -> str:
        return (
            f"{self.name} online. "
            "Type 'help' for commands, or ask me anything and I will respond."
        )

    def respond(self, text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return "Awaiting your instruction."

        command = cleaned.lower()
        if command in self._commands:
            return self._commands[command]()

        if any(word in command for word in ("hello", "hi", "hey")):
            return "Hello. Friday is at your service."
        if "your name" in command:
            return "I am Friday, your personal AI assistant."

        return (
            "Command acknowledged. I can currently handle: "
            "help, time, date, status, exit."
        )

    @staticmethod
    def _time() -> str:
        return f"Current time: {datetime.now().strftime('%H:%M:%S')}"

    @staticmethod
    def _date() -> str:
        return f"Today's date: {datetime.now().strftime('%Y-%m-%d')}"

    @staticmethod
    def _status() -> str:
        return "All systems operational."

    @staticmethod
    def _exit_text() -> str:
        return "Shutting down Friday. Goodbye."

    @staticmethod
    def _help() -> str:
        return dedent(
            """
            Available commands:
              - help   : Show this menu
              - time   : Show current local time
              - date   : Show current local date
              - status : Show assistant status
              - exit   : Exit Friday
            """
        ).strip()


def run() -> None:
    friday = Friday()
    print(friday.greet())
    while True:
        user_input = input("You> ")
        reply = friday.respond(user_input)
        print(f"Friday> {reply}")
        if user_input.strip().lower() in {"exit", "quit"}:
            break


if __name__ == "__main__":
    run()
