"""
Unit tests for llm_router.py.
Validates LLM routing, JSON parsing robustness, and elimination of retired GitHub endpoints.
"""
import unittest
from llm_router import parse_json_safely, get_engine_options, is_google_available, is_groq_available

class TestLLMRouter(unittest.TestCase):

    def test_github_models_omitted(self):
        engines = get_engine_options()
        for eng in engines:
            self.assertNotIn("github", eng.lower(), "Retired GitHub Models inference endpoint must not be present in active options")

    def test_parse_json_safely_clean_dict(self):
        raw = '{"status": "ok", "count": 42}'
        parsed = parse_json_safely(raw)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("status"), "ok")
        self.assertEqual(parsed.get("count"), 42)

    def test_parse_json_safely_markdown_wrapped(self):
        raw = """```json
        {
            "sql": "SELECT * FROM transactions",
            "companion_filter": "Direction = 'Out'"
        }
        ```"""
        parsed = parse_json_safely(raw)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("sql"), "SELECT * FROM transactions")

    def test_parse_json_safely_array(self):
        raw = """```json
        [
            {"Date": "2026-01-01", "Amount": 10.50},
            {"Date": "2026-01-02", "Amount": 20.00}
        ]
        ```"""
        parsed = parse_json_safely(raw)
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 2)

    def test_parse_json_safely_corrupt_input(self):
        raw = "This is not json at all."
        with self.assertRaises(ValueError):
            parse_json_safely(raw)

    def test_provider_availability_functions(self):
        # Functions should execute cleanly without raising exceptions
        g_avail = is_google_available()
        groq_avail = is_groq_available()
        self.assertIsInstance(g_avail, bool)
        self.assertIsInstance(groq_avail, bool)

if __name__ == "__main__":
    unittest.main()
