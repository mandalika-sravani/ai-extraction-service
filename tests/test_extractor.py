"""Tests run with a fake client, so no API key or tokens are needed."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extractor import ExtractionError, Extractor
from schemas import ContactList


def tool_response(data, name="save_contactlist", stop="tool_use"):
    block = NS(type="tool_use", id="toolu_1", name=name, input=data)
    return NS(content=[block], stop_reason=stop)


class FakeClient:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


GOOD = {"contacts": [{"name": "Priya Sharma", "email": "Priya@Nimbus.io",
                      "phone": "+91 98480 22334", "company": "Nimbus", "job_title": None}]}
BAD = {"contacts": [{"name": "Priya Sharma", "email": "not-an-email"}]}


class TestExtractor(unittest.TestCase):
    def test_happy_path_normalises_fields(self):
        out = Extractor(ContactList, client=FakeClient([tool_response(GOOD)])).extract("text")
        c = out.contacts[0]
        self.assertEqual(c.email, "priya@nimbus.io")
        self.assertEqual(c.phone, "+919848022334")


    def test_tool_offered_with_auto_choice(self):
        client = FakeClient([tool_response(GOOD)])
        Extractor(ContactList, client=client).extract("text")
        self.assertEqual(client.calls[0]["tool_choice"], {"type": "auto"})
        self.assertEqual(client.calls[0]["tools"][0]["name"], "save_contactlist")


    def test_retries_with_error_feedback_then_succeeds(self):
        client = FakeClient([tool_response(BAD), tool_response(GOOD)])
        out = Extractor(ContactList, client=client).extract("text")
        self.assertEqual(len(out.contacts), 1)
        self.assertEqual(len(client.calls), 2)
        feedback = client.calls[1]["messages"][-1]["content"][0]
        self.assertEqual(feedback["type"], "tool_result")
        self.assertIs(feedback["is_error"], True)


    def test_gives_up_after_max_retries(self):
        client = FakeClient([tool_response(BAD)] * 3)
        with self.assertRaisesRegex(ExtractionError, "after 3 attempts"):
            Extractor(ContactList, client=client, max_retries=2).extract("text")


    def test_rejects_bad_input(self):
        for text in ("", "   ", "x" * 20_001):
            with self.subTest(text_length=len(text)):
                with self.assertRaises(ExtractionError):
                    Extractor(ContactList, client=FakeClient([])).extract(text)


    def test_truncated_response(self):
        client = FakeClient([tool_response(GOOD, stop="max_tokens")])
        with self.assertRaisesRegex(ExtractionError, "cut off"):
            Extractor(ContactList, client=client).extract("text")


TEXT_REPLY = NS(content=[NS(type="text", text="Here are the contacts...")], stop_reason="end_turn")


def test_nudges_when_tool_not_called_then_succeeds(self):
    client = FakeClient([TEXT_REPLY, tool_response(GOOD)])
    out = Extractor(ContactList, client=client).extract("text")
    self.assertEqual(len(out.contacts), 1)
    self.assertIn("must call", client.calls[1]["messages"][-1]["content"])


def test_gives_up_if_tool_never_called(self):
    client = FakeClient([TEXT_REPLY] * 3)
    with self.assertRaisesRegex(ExtractionError, "after 3 attempts"):
        Extractor(ContactList, client=client).extract("text")
