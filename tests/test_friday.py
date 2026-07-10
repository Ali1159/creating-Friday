from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from friday import Friday


class FridayTests(unittest.TestCase):
    def test_calc_with_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assistant = Friday(root_dir=Path(tmp), input_func=lambda _: "n")
            result = assistant.respond("calc 5 * (8 + 2)")
            self.assertEqual(result, "Result: 50")

    def test_todo_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assistant = Friday(root_dir=root, input_func=lambda _: "n")
            self.assertEqual(assistant.respond("todo add buy milk"), "Todo added.")
            listing = assistant.respond("todo list")
            self.assertIn("[ ] buy milk", listing)

            assistant2 = Friday(root_dir=root, input_func=lambda _: "n")
            listing2 = assistant2.respond("todo list")
            self.assertIn("[ ] buy milk", listing2)

    def test_reminder_router(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assistant = Friday(root_dir=Path(tmp), input_func=lambda _: "n")
            response = assistant.respond("remind 1m drink water")
            self.assertIn("Reminder set for", response)
            due_list = assistant.respond("due")
            self.assertIn("Reminder", due_list)

    def test_plugin_permission_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assistant = Friday(root_dir=Path(tmp), input_func=lambda _: "n")
            result = assistant.respond("plugin run list_files")
            self.assertEqual(result, "Action denied by safety policy.")


if __name__ == "__main__":
    unittest.main()
