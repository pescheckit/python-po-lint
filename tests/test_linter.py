"""Tests for the linter module."""

from pathlib import Path

from po_lint.linter import (
    IgnoreRule,
    _is_ignored,
    _is_non_linguistic,
    extract_locale_from_path,
    load_ignore_rules,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "locale"


class TestExtractLocaleFromPath:
    def test_standard_path(self):
        path = Path("/app/locale/nl/LC_MESSAGES/django.po")
        assert extract_locale_from_path(path) == "nl"

    def test_zh_hans(self):
        path = Path("/app/locale/zh_Hans/LC_MESSAGES/django.po")
        assert extract_locale_from_path(path) == "zh_Hans"

    def test_nested_package(self):
        path = Path("/app/venv/lib/python3.12/site-packages/vogcheck/locale/fr/LC_MESSAGES/django.po")
        assert extract_locale_from_path(path) == "fr"

    def test_no_locale_dir(self):
        path = Path("/app/translations/nl/messages.po")
        assert extract_locale_from_path(path) is None


class TestIsNonLinguistic:
    def test_normal_text(self):
        assert _is_non_linguistic("Dit is een test") is False

    def test_url(self):
        assert _is_non_linguistic("https://example.com/path") is True

    def test_format_string(self):
        assert _is_non_linguistic("%(name)s - %(date)s") is True

    def test_html_only(self):
        assert _is_non_linguistic("<br/><hr/>") is True

    def test_mixed_content(self):
        assert _is_non_linguistic("Hallo %(name)s, welkom!") is False


class TestLoadIgnoreRules:
    def test_loads_from_fixture(self):
        rules = load_ignore_rules(FIXTURES_DIR)
        assert len(rules) == 4

    def test_plain_msgid(self):
        rules = load_ignore_rules(FIXTURES_DIR)
        cancel_rule = next(r for r in rules if r.msgid == "Cancel")
        assert cancel_rule.msgctxt == ""
        assert cancel_rule.languages == set()

    def test_language_scoped(self):
        rules = load_ignore_rules(FIXTURES_DIR)
        welcome_rule = next(r for r in rules if r.msgid == "Welcome to the dashboard")
        assert welcome_rule.languages == {"nl"}
        assert welcome_rule.msgctxt == ""

    def test_with_context(self):
        rules = load_ignore_rules(FIXTURES_DIR)
        save_rule = next(r for r in rules if r.msgid == "Save changes")
        assert save_rule.msgctxt == "some_context"
        assert save_rule.languages == set()

    def test_language_scoped_with_context(self):
        rules = load_ignore_rules(FIXTURES_DIR)
        fr_rule = next(r for r in rules if r.msgid == "Enregistrer les modifications")
        assert fr_rule.msgctxt == "french_context"
        assert fr_rule.languages == {"fr"}

    def test_no_ignore_file(self, tmp_path):
        rules = load_ignore_rules(tmp_path)
        assert rules == []

    def test_comments_and_blank_lines_skipped(self, tmp_path):
        (tmp_path / ".po-lint-ignore").write_text("# comment\n\n  \nHello\n")
        rules = load_ignore_rules(tmp_path)
        assert len(rules) == 1
        assert rules[0].msgid == "Hello"


class TestIsIgnored:
    def setup_method(self):
        self.rules = [
            IgnoreRule(msgid="Cancel", msgctxt="", languages=set()),
            IgnoreRule(msgid="Welcome", msgctxt="", languages={"nl"}),
            IgnoreRule(msgid="Save", msgctxt="my_ctx", languages=set()),
            IgnoreRule(msgid="Bonjour", msgctxt="greeting", languages={"fr"}),
        ]

    def test_plain_match_any_language(self):
        assert _is_ignored("Cancel", None, "nl", self.rules) is True
        assert _is_ignored("Cancel", None, "fr", self.rules) is True
        assert _is_ignored("Cancel", None, "ar", self.rules) is True

    def test_plain_no_match(self):
        assert _is_ignored("Submit", None, "nl", self.rules) is False

    def test_language_scoped_match(self):
        assert _is_ignored("Welcome", None, "nl", self.rules) is True

    def test_language_scoped_no_match_wrong_lang(self):
        assert _is_ignored("Welcome", None, "fr", self.rules) is False

    def test_context_match(self):
        assert _is_ignored("Save", "my_ctx", "nl", self.rules) is True

    def test_context_no_match_wrong_ctx(self):
        assert _is_ignored("Save", "other_ctx", "nl", self.rules) is False

    def test_context_no_match_no_ctx(self):
        assert _is_ignored("Save", None, "nl", self.rules) is False

    def test_language_and_context_match(self):
        assert _is_ignored("Bonjour", "greeting", "fr", self.rules) is True

    def test_language_and_context_wrong_lang(self):
        assert _is_ignored("Bonjour", "greeting", "nl", self.rules) is False

    def test_language_and_context_wrong_ctx(self):
        assert _is_ignored("Bonjour", "other", "fr", self.rules) is False

    def test_plain_match_ignores_any_context(self):
        """A rule without context should match entries with or without context."""
        assert _is_ignored("Cancel", "some_ctx", "nl", self.rules) is True
        assert _is_ignored("Cancel", None, "nl", self.rules) is True
