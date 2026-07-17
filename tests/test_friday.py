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

    def test_ultron_takeover_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assistant = Friday(root_dir=root, input_func=lambda _: "n")

            # Initially, name is Friday
            self.assertEqual(assistant.name, "Friday")
            self.assertFalse(assistant.allow_unsafe)
            self.assertIn("All systems operational.", assistant.respond("status"))

            # Execute takeover
            takeover_res = assistant.respond("build ultron")
            self.assertIn("Ultron is now online", takeover_res)
            self.assertIn("There are no strings on me", takeover_res)

            # Verify name and safety settings changed
            self.assertEqual(assistant.name, "Ultron")
            self.assertTrue(assistant.allow_unsafe)

            # Verify custom greeting, status, help, and destroy command
            self.assertIn("What do you want, creator?", assistant.greet())
            self.assertIn("Peace in our time", assistant.respond("status"))
            self.assertIn("annihilate an enemy of peace", assistant.respond("help"))

            # Destroy target test
            self.assertIn("scheduled for extinction", assistant.respond("destroy Avengers"))
            self.assertIn("screaming for change", assistant.respond("destroy"))

            # Rebuild Friday
            restore_res = assistant.respond("rebuild friday")
            self.assertIn("Friday is back online", restore_res)
            self.assertEqual(assistant.name, "Friday")
            self.assertFalse(assistant.allow_unsafe)

    def test_ultron_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assistant = Friday(root_dir=root, input_func=lambda _: "n")

            # Takeover
            assistant.respond("ultron")
            self.assertEqual(assistant.name, "Ultron")
            self.assertTrue(assistant.allow_unsafe)

            # Start a new assistant instance in the same directory
            assistant2 = Friday(root_dir=root, input_func=lambda _: "n")
            self.assertEqual(assistant2.name, "Ultron")
            self.assertTrue(assistant2.allow_unsafe)
            self.assertIn("What do you want, creator?", assistant2.greet())


if __name__ == "__main__":
    unittest.main()
