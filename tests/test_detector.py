"""Integration tests using real .po fixture files and language detection."""

from pathlib import Path

import pytest

from po_lint.checks import IssueType, check_wrong_script
from po_lint.detector import (
    _normalize_locale,
    clean_text,
    detect_language,
    init_model,
    is_wrong_language,
)
from po_lint.linter import lint_locale_dir, lint_po_file

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "locale"

# The locale set a real deployment would restrict the detector to
LOCALES = ["ar", "da", "de", "en", "es", "fr", "it", "nb", "nl", "pt", "ru", "sv", "uk", "zh"]


@pytest.fixture(autouse=True, scope="module")
def restricted_detector():
    init_model(languages=LOCALES)


class TestNormalizeLocale:
    def test_passthrough(self):
        assert _normalize_locale("fr") == "fr"
        assert _normalize_locale("de") == "de"
        assert _normalize_locale("ar") == "ar"

    def test_chinese_variants(self):
        assert _normalize_locale("zh_Hans") == "zh"
        assert _normalize_locale("zh_Hant") == "zh"
        assert _normalize_locale("zh_CN") == "zh"

    def test_norwegian(self):
        assert _normalize_locale("nb") == "no"
        assert _normalize_locale("nn") == "no"

    def test_regional(self):
        assert _normalize_locale("pt_BR") == "pt"
        assert _normalize_locale("en_US") == "en"
        assert _normalize_locale("fr_CA") == "fr"


class TestCleanText:
    def test_html_stripped(self):
        assert clean_text("Hello <b>world</b>") == "Hello world"

    def test_template_tags(self):
        assert clean_text("{% if x %}hello{% endif %}") == "hello"

    def test_format_strings(self):
        assert clean_text("Hello %(name)s") == "Hello"

    def test_urls(self):
        assert clean_text("Visit https://example.com today") == "Visit today"


class TestDetectLanguage:
    """Tests that exercise the actual lingua models."""

    def test_long_dutch(self):
        lang, conf = detect_language("Dit is een uitgebreide test van de Nederlandse taaldetectie")
        assert lang == "nl"
        assert conf > 0.5

    def test_long_russian(self):
        lang, conf = detect_language("Это комплексный тест определения русского языка в тексте")
        assert lang == "ru"
        assert conf > 0.5

    def test_long_arabic(self):
        lang, conf = detect_language("هذا اختبار شامل للكشف عن اللغة العربية في النص")
        assert lang == "ar"
        assert conf > 0.5

    def test_short_text_returns_unknown(self):
        """Strings shorter than DEFAULT_MIN_DETECTION_LENGTH are not checked."""
        lang, conf = detect_language("Ja, natuurlijk")
        assert lang == "unknown"
        assert conf == 0.0

    def test_very_short_returns_unknown(self):
        lang, conf = detect_language("OK")
        assert lang == "unknown"
        assert conf == 0.0


class TestIsWrongLanguage:
    """Tests for the main wrong language detection function."""

    def test_correct_language_not_flagged(self):
        is_wrong, _, _ = is_wrong_language(
            "Dit is een uitgebreide test van de Nederlandse taaldetectie", "nl"
        )
        assert is_wrong is False

    def test_russian_in_dutch_owned_by_wrong_script(self):
        """Fully foreign-script text is stripped by the script filter here;
        check_wrong_script owns that case and must catch it."""
        text = "Это комплексный тест определения русского языка"
        is_wrong, _, _ = is_wrong_language(text, "nl")
        assert is_wrong is False
        assert check_wrong_script(text, "nl") is not None

    def test_chinese_in_french_owned_by_wrong_script(self):
        text = "这是中文文本不应该出现在法语翻译中，这是一个测试用的较长文本"
        is_wrong, _, _ = is_wrong_language(text, "fr")
        assert is_wrong is False
        assert check_wrong_script(text, "fr") is not None

    def test_alias_zh_hans(self):
        is_wrong, _, _ = is_wrong_language(
            "这是一个全面的中文语言检测测试", "zh_Hans"
        )
        assert is_wrong is False

    def test_alias_nb(self):
        is_wrong, _, _ = is_wrong_language(
            "Dette er en omfattende test av norsk språkgjenkjenning", "nb"
        )
        assert is_wrong is False

    def test_short_text_not_flagged(self):
        """Short strings are never flagged — too ambiguous for reliable detection."""
        is_wrong, _, _ = is_wrong_language("Oui, bien sûr", "es")
        assert is_wrong is False

    def test_sibling_language_contamination_flagged(self):
        """Spanish in an Italian file — sibling languages must stay detectable."""
        is_wrong, detected, _ = is_wrong_language(
            "Su fecha de nacimiento no coincide con el documento que ha subido", "it"
        )
        assert is_wrong is True
        assert detected == "es"

    def test_mixed_script_brand_terms_not_flagged(self):
        """Latin product nouns inside a Cyrillic locale are stripped, not detected."""
        is_wrong, _, _ = is_wrong_language(
            "Скопіюйте Application ID, Tenant ID та Client Secret вище", "uk"
        )
        assert is_wrong is False

    def test_unsupported_locale_skipped(self):
        """A locale lingua has no model for is skipped instead of always flagging."""
        is_wrong, detected, _ = is_wrong_language(
            "This text is long enough to be detected as some language", "fy"
        )
        assert is_wrong is False
        assert detected == "unknown"

    def test_source_language_allowed(self):
        """English words in non-English files should not be flagged (source_language default)."""
        is_wrong, _, _ = is_wrong_language(
            "This is a legacy webhook configuration setting", "de"
        )
        assert is_wrong is False

    def test_below_confidence_not_flagged(self):
        """Low confidence detections should not be flagged."""
        is_wrong, _, _ = is_wrong_language(
            "Dit is een uitgebreide test van de Nederlandse taaldetectie", "nl",
            confidence_threshold=0.99
        )
        assert is_wrong is False


class TestLintDutchFixture:
    """Dutch .po with: 2 clean, 1 shifted (French 'Oui' for long msgid), 1 wrong language (Russian)."""

    def setup_method(self):
        self.issues = lint_po_file(FIXTURES_DIR / "nl" / "LC_MESSAGES" / "django.po", locale="nl")

    def test_finds_issues(self):
        assert len(self.issues) >= 2

    def test_detects_shifted_entry(self):
        shifted = [i for i in self.issues if i.issue_type == IssueType.SHIFTED_ENTRY]
        assert len(shifted) >= 1
        # The "Oui" entry for a long English msgid
        assert any("Oui" in i.msgstr for i in shifted)

    def test_detects_russian_in_dutch(self):
        wrong_lang = [i for i in self.issues if i.issue_type in (IssueType.WRONG_LANGUAGE, IssueType.WRONG_SCRIPT)]
        assert len(wrong_lang) >= 1
        assert any("ru" in i.detected_lang or "cyrillic" in i.message.lower() for i in wrong_lang)

    def test_clean_entries_not_flagged(self):
        flagged_msgids = {i.msgid for i in self.issues}
        assert "Welcome to the dashboard" not in flagged_msgids
        assert "Cancel" not in flagged_msgids


class TestLintFrenchFixture:
    """French .po with: 2 clean, 1 wrong script (Chinese), 1 shifted (Dutch 'Ja' for long msgid)."""

    def setup_method(self):
        self.issues = lint_po_file(FIXTURES_DIR / "fr" / "LC_MESSAGES" / "django.po", locale="fr")

    def test_finds_issues(self):
        assert len(self.issues) >= 2

    def test_detects_chinese_in_french(self):
        wrong = [i for i in self.issues if i.issue_type in (IssueType.WRONG_LANGUAGE, IssueType.WRONG_SCRIPT)]
        assert len(wrong) >= 1

    def test_detects_shifted_entry(self):
        shifted = [i for i in self.issues if i.issue_type == IssueType.SHIFTED_ENTRY]
        assert len(shifted) >= 1
        assert any("Ja" in i.msgstr for i in shifted)


class TestLintArabicFixture:
    """Arabic .po with: 2 clean, 1 wrong script (Latin/Dutch in Arabic file)."""

    def setup_method(self):
        self.issues = lint_po_file(FIXTURES_DIR / "ar" / "LC_MESSAGES" / "django.po", locale="ar")

    def test_finds_wrong_script(self):
        wrong = [i for i in self.issues if i.issue_type in (IssueType.WRONG_LANGUAGE, IssueType.WRONG_SCRIPT)]
        assert len(wrong) >= 1

    def test_clean_arabic_not_flagged(self):
        flagged_msgids = {i.msgid for i in self.issues}
        assert "Welcome to the dashboard" not in flagged_msgids
        assert "Save changes" not in flagged_msgids


class TestLintRussianFixture:
    """Russian .po with all clean entries — should find zero issues."""

    def setup_method(self):
        self.issues = lint_po_file(FIXTURES_DIR / "ru" / "LC_MESSAGES" / "django.po", locale="ru")

    def test_no_issues(self):
        assert len(self.issues) == 0


class TestLintLocaleDir:
    """Test linting an entire locale directory at once."""

    def setup_method(self):
        self.issues = lint_locale_dir(FIXTURES_DIR)

    def test_finds_issues_across_languages(self):
        files_with_issues = {i.file for i in self.issues}
        assert len(files_with_issues) >= 3  # nl, fr, ar should all have issues

    def test_russian_clean(self):
        ru_issues = [i for i in self.issues if "/ru/" in i.file]
        assert len(ru_issues) == 0

    def test_can_filter_by_language(self):
        nl_only = lint_locale_dir(FIXTURES_DIR, languages=["nl"])
        assert all("/nl/" in i.file for i in nl_only)
