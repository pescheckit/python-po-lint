"""Tests for the structural checks (no model loading needed)."""

from po_lint.checks import (
    IssueType,
    check_garbled_text,
    check_shifted_entry,
    check_wrong_script,
    detect_scripts,
)


class TestDetectScripts:
    def test_latin(self):
        scripts = detect_scripts("Hello world")
        assert "latin" in scripts

    def test_cyrillic(self):
        scripts = detect_scripts("Привет мир")
        assert "cyrillic" in scripts

    def test_arabic(self):
        scripts = detect_scripts("مرحبا بالعالم")
        assert "arabic" in scripts

    def test_cjk(self):
        scripts = detect_scripts("你好世界")
        assert "cjk" in scripts

    def test_devanagari(self):
        scripts = detect_scripts("नमस्ते दुनिया")
        assert "devanagari" in scripts

    def test_mixed(self):
        scripts = detect_scripts("Hello Привет 你好")
        assert "latin" in scripts
        assert "cyrillic" in scripts
        assert "cjk" in scripts


class TestCheckWrongScript:
    def test_correct_latin_for_dutch(self):
        assert check_wrong_script("Dit is een test", "nl") is None

    def test_correct_cyrillic_for_russian(self):
        assert check_wrong_script("Это тест", "ru") is None

    def test_correct_arabic_for_arabic(self):
        assert check_wrong_script("هذا اختبار", "ar") is None

    def test_cyrillic_in_dutch(self):
        issue = check_wrong_script("Это тест для голландского", "nl")
        assert issue is not None
        assert issue.issue_type == IssueType.WRONG_SCRIPT

    def test_arabic_in_french(self):
        issue = check_wrong_script("هذا اختبار للفرنسية", "fr")
        assert issue is not None
        assert issue.issue_type == IssueType.WRONG_SCRIPT

    def test_allows_mixed_with_dominant_correct(self):
        # Latin text with a few Cyrillic chars (e.g. brand name) should be fine for Dutch
        assert check_wrong_script("Dit is een test met Москва erin", "nl") is None

    def test_unknown_locale_skips(self):
        assert check_wrong_script("Some text", "xx_UNKNOWN") is None

    def test_multi_script_language(self):
        # Serbian accepts both Cyrillic and Latin
        assert check_wrong_script("Ovo je test", "sr") is None
        assert check_wrong_script("Ово је тест", "sr") is None

    def test_russian_chars_in_ukrainian(self):
        # "ы" is Russian-only — should be flagged in Ukrainian file
        issue = check_wrong_script("Пожалуйста, загрузите только файлы", "uk")
        assert issue is not None
        assert issue.issue_type == IssueType.WRONG_SCRIPT
        assert "ru" in issue.message

    def test_mixed_uk_ru_chars_flagged(self):
        # Both Ukrainian "і" and Russian "ы" — contamination
        issue = check_wrong_script("файли і документы", "uk")
        assert issue is not None
        assert "contamination" in issue.message

    def test_ukrainian_chars_in_russian(self):
        # "і" is Ukrainian-only — should be flagged in Russian file
        issue = check_wrong_script("Будь ласка, додайте назву і пакету", "ru")
        assert issue is not None
        assert "uk" in issue.message

    def test_valid_ukrainian_not_flagged(self):
        # Pure Ukrainian with "і" — should be fine
        assert check_wrong_script("Будь ласка, додайте назву пакету", "uk") is None

    def test_valid_ukrainian_with_own_chars(self):
        # Ukrainian with its own distinctive chars — fine
        assert check_wrong_script("Тему майстра кандідата успішно оновлено", "uk") is None

    def test_no_distinctive_chars_not_flagged(self):
        # Shared Cyrillic without distinctive chars from either side — can't tell, skip
        assert check_wrong_script("Будь ласка", "uk") is None


class TestCheckShiftedEntry:
    def test_normal_entry(self):
        assert check_shifted_entry("Hello world", "Hallo wereld") is None

    def test_short_msgid_ignored(self):
        assert check_shifted_entry("Short", "S") is None

    def test_shifted_detected(self):
        long_msgid = "A" * 200
        short_msgstr = "Yes"
        issue = check_shifted_entry(long_msgid, short_msgstr)
        assert issue is not None
        assert issue.issue_type == IssueType.SHIFTED_ENTRY

    def test_proportional_translation_ok(self):
        long_msgid = "A" * 200
        proportional_msgstr = "B" * 50  # 25% — above threshold
        assert check_shifted_entry(long_msgid, proportional_msgstr) is None

    def test_empty_msgstr(self):
        assert check_shifted_entry("Hello", "") is None


class TestCheckGarbledText:
    def test_normal_text(self):
        assert check_garbled_text("Dit is een normale tekst") is None

    def test_short_text_skipped(self):
        assert check_garbled_text("Hi") is None

    def test_replacement_characters(self):
        garbled = "\ufffd" * 10 + "abc"
        issue = check_garbled_text(garbled)
        assert issue is not None
        assert issue.issue_type == IssueType.GARBLED_TEXT
