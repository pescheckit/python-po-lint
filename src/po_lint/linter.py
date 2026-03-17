"""Main linter that ties all checks together and walks locale directories."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import polib

from po_lint.checks import (
    Issue,
    IssueType,
    Severity,
    check_garbled_text,
    check_shifted_entry,
    check_wrong_script,
)
from po_lint.detector import DEFAULT_MIN_DETECTION_LENGTH, is_wrong_language

log = logging.getLogger(__name__)

IGNORE_FILE = ".po-lint-ignore"


@dataclass
class IgnoreRule:
    """A single ignore rule from .po-lint-ignore."""

    msgid: str
    msgctxt: str  # Empty string means match any context
    languages: set[str]  # Empty set means match all languages


def load_ignore_rules(locale_dir: Path) -> list[IgnoreRule]:
    """Load ignore rules from a .po-lint-ignore file in the locale directory.

    Format:
      # Comment
      Some msgid                              → ignore for all languages, any context
      [ar,hi] Some msgid                      → ignore only for Arabic and Hindi
      screening status::Some msgid            → ignore with specific msgctxt
      [ar] screening status::Some msgid       → both language scope and context
    """
    ignore_file = locale_dir / IGNORE_FILE
    if not ignore_file.exists():
        return []

    rules = []
    for line in ignore_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        languages: set[str] = set()
        # Parse optional language scope: [ar,hi,zh_Hans]
        if line.startswith("["):
            bracket_end = line.index("]")
            lang_str = line[1:bracket_end]
            languages = {lang.strip() for lang in lang_str.split(",")}
            line = line[bracket_end + 1:].strip()

        # Parse optional context: msgctxt::msgid
        if "::" in line:
            msgctxt, msgid = line.split("::", 1)
        else:
            msgctxt = ""
            msgid = line

        rules.append(IgnoreRule(msgid=msgid, msgctxt=msgctxt, languages=languages))

    return rules


def _is_ignored(msgid: str, msgctxt: str | None, locale: str, ignore_rules: list[IgnoreRule]) -> bool:
    """Check if an entry matches any ignore rule."""
    for rule in ignore_rules:
        # Check language scope
        if rule.languages and locale not in rule.languages:
            continue
        # Check msgid
        if rule.msgid != msgid:
            continue
        # Check context
        if rule.msgctxt and rule.msgctxt != (msgctxt or ""):
            continue
        return True
    return False


def extract_locale_from_path(po_file: Path) -> str | None:
    """Extract the locale code from a .po file path.

    Expects paths like: .../locale/<lang>/LC_MESSAGES/django.po
    """
    parts = po_file.parts
    for i, part in enumerate(parts):
        if part == "LC_MESSAGES" and i >= 1:
            return parts[i - 1]
        if part == "locale" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _find_locale_root(po_file: Path) -> Path | None:
    """Find the locale/ directory that contains this .po file."""
    for parent in po_file.parents:
        if parent.name == "locale":
            return parent
    return None


def lint_po_file(
    po_file: Path,
    locale: str | None = None,
    source_language: str = "en",
    confidence_threshold: float = 0.5,
    min_text_length: int = 3,
    min_detection_length: int = DEFAULT_MIN_DETECTION_LENGTH,
    ignore_patterns: list[str] | None = None,
    ignore_rules: list[IgnoreRule] | None = None,
    check_untranslated: bool = True,
) -> list[Issue]:
    """Lint a single .po file and return all issues found."""
    if locale is None:
        locale = extract_locale_from_path(po_file)
    if locale is None:
        return []

    compiled_ignores = [re.compile(p) for p in (ignore_patterns or [])]
    ignore_rules = ignore_rules or []

    try:
        catalog = polib.pofile(str(po_file))
    except (OSError, SyntaxError) as e:
        return [
            Issue(
                file=str(po_file),
                line=0,
                msgid="",
                msgstr="",
                issue_type=IssueType.GARBLED_TEXT,
                severity=Severity.ERROR,
                message=f"Failed to parse .po file: {e}",
            )
        ]

    issues = []

    # Check for untranslated entries (skip source language)
    if check_untranslated and locale != source_language:
        for entry in catalog.untranslated_entries():
            if entry.obsolete:
                continue
            issues.append(
                Issue(
                    file=str(po_file),
                    line=entry.linenum,
                    msgid=entry.msgid,
                    msgstr="",
                    issue_type=IssueType.UNTRANSLATED,
                    severity=Severity.WARNING,
                    message="Missing translation",
                )
            )

    for entry in catalog.translated_entries():
        msgid = entry.msgid
        msgstr = entry.msgstr

        if not msgstr or len(msgstr.strip()) < min_text_length:
            continue

        # Skip entries in the ignore file
        if _is_ignored(msgid, entry.msgctxt, locale, ignore_rules):
            continue

        # Skip entries matching ignore patterns
        if any(p.search(msgid) or p.search(msgstr) for p in compiled_ignores):
            continue

        # Skip entries that are mostly format strings / placeholders / URLs
        if _is_non_linguistic(msgstr):
            continue

        # Skip entries where the translation is identical to the source
        # (intentionally untranslated — common for brand names, acronyms, technical terms)
        if msgid == msgstr:
            continue

        # 1. Wrong script check (fast, no model needed)
        issue = check_wrong_script(msgstr, locale)
        if issue:
            issue.file = str(po_file)
            issue.line = entry.linenum
            issue.msgid = msgid
            issues.append(issue)
            continue  # If wrong script, skip language detection (it would also flag)

        # 2. Garbled text check
        issue = check_garbled_text(msgstr)
        if issue:
            issue.file = str(po_file)
            issue.line = entry.linenum
            issue.msgid = msgid
            issues.append(issue)
            continue

        # 3. Shifted entry check
        issue = check_shifted_entry(msgid, msgstr)
        if issue:
            issue.file = str(po_file)
            issue.line = entry.linenum
            issues.append(issue)

        # 4. Wrong language check (uses fastText)
        is_wrong, detected_lang, confidence = is_wrong_language(
            msgstr, locale, confidence_threshold, source_language, msgid=msgid,
            min_detection_length=min_detection_length,
        )
        if is_wrong:
            issues.append(
                Issue(
                    file=str(po_file),
                    line=entry.linenum,
                    msgid=msgid,
                    msgstr=msgstr,
                    issue_type=IssueType.WRONG_LANGUAGE,
                    severity=Severity.ERROR,
                    message=f"Expected {locale}, detected {detected_lang} (confidence: {confidence:.0%})",
                    detected_lang=detected_lang,
                    confidence=confidence,
                )
            )

    return issues


def _is_non_linguistic(text: str) -> bool:
    """Check if text is mostly non-linguistic (URLs, format strings, numbers, etc.)."""
    cleaned = text
    # Strip Django/Python format strings
    cleaned = re.sub(r"%\([^)]+\)[sd]", "", cleaned)
    cleaned = re.sub(r"%[sd]", "", cleaned)
    cleaned = re.sub(r"\{[^}]*\}", "", cleaned)
    # Strip HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    # Strip URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    # Strip numbers and punctuation
    cleaned = re.sub(r"[0-9.,;:!?/\\@#$%^&*()_+=\[\]{}<>\"'\-\s]", "", cleaned)
    # If very little text remains, it's non-linguistic
    return len(cleaned) < 3


def detect_source_language(locale_dir: Path) -> str | None:
    """Auto-detect the source language from a locale directory.

    A locale is the source language if:
    - It has .po files with at least one entry
    - ALL entries across ALL its .po files are untranslated (empty msgstr)
    - Exactly one locale in the directory matches this condition

    Returns the locale code if exactly one match, None otherwise.
    """
    # Collect per-locale stats: (total_entries, total_untranslated)
    locale_stats: dict[str, tuple[int, int]] = {}

    for po_file in sorted(locale_dir.rglob("*.po")):
        locale = extract_locale_from_path(po_file)
        if locale is None:
            continue
        try:
            catalog = polib.pofile(str(po_file))
        except (OSError, SyntaxError):
            continue

        total = len(catalog.translated_entries()) + len(catalog.untranslated_entries())
        untranslated = len(catalog.untranslated_entries())

        prev_total, prev_untranslated = locale_stats.get(locale, (0, 0))
        locale_stats[locale] = (prev_total + total, prev_untranslated + untranslated)

    # Find locales where every entry is untranslated (and there are entries)
    candidates = [
        loc for loc, (total, untranslated) in locale_stats.items()
        if total > 0 and total == untranslated
    ]

    if len(candidates) == 1:
        log.debug("Auto-detected source language: %s", candidates[0])
        return candidates[0]

    return None


def lint_locale_dir(
    locale_dir: Path,
    languages: list[str] | None = None,
    source_language: str = "en",
    confidence_threshold: float = 0.5,
    min_text_length: int = 3,
    min_detection_length: int = DEFAULT_MIN_DETECTION_LENGTH,
    ignore_patterns: list[str] | None = None,
    check_untranslated: bool = True,
) -> list[Issue]:
    """Lint all .po files in a locale directory.

    Loads .po-lint-ignore from the locale directory if present.

    Args:
        locale_dir: Path to a locale/ directory containing <lang>/LC_MESSAGES/*.po
        languages: If set, only lint these language codes. If empty, lint all.
        source_language: The source language of the .po files (default: "en").
        confidence_threshold: Minimum confidence to flag a wrong language.
        min_text_length: Minimum msgstr length to check.
        ignore_patterns: Regex patterns for msgid/msgstr to skip.
        check_untranslated: If True, flag entries with empty msgstr.
    """
    ignore_rules = load_ignore_rules(locale_dir)

    # Auto-detect source language as fallback
    detected_source = detect_source_language(locale_dir)
    effective_source = detected_source or source_language

    issues = []

    for po_file in sorted(locale_dir.rglob("*.po")):
        locale = extract_locale_from_path(po_file)
        if locale is None:
            continue
        if languages and locale not in languages:
            continue

        file_issues = lint_po_file(
            po_file,
            locale=locale,
            source_language=effective_source,
            confidence_threshold=confidence_threshold,
            min_text_length=min_text_length,
            min_detection_length=min_detection_length,
            ignore_patterns=ignore_patterns,
            ignore_rules=ignore_rules,
            check_untranslated=check_untranslated,
        )
        issues.extend(file_issues)

    return issues
