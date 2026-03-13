"""Individual lint checks for .po file entries."""

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


class IssueType(Enum):
    WRONG_LANGUAGE = "wrong_language"
    WRONG_SCRIPT = "wrong_script"
    SHIFTED_ENTRY = "shifted_entry"
    GARBLED_TEXT = "garbled_text"
    UNTRANSLATED = "untranslated"


@dataclass
class Issue:
    """A single lint issue found in a .po file."""

    file: str
    line: int
    msgid: str
    msgstr: str
    issue_type: IssueType
    severity: Severity
    message: str
    detected_lang: str = ""
    confidence: float = 0.0

    def __str__(self) -> str:
        msgid_short = self.msgid[:60] + "..." if len(self.msgid) > 60 else self.msgid
        return f"  {self.severity.value.upper()}: [{self.issue_type.value}] {self.message}\n    msgid: {msgid_short!r}"


# Script detection patterns — covers all major writing systems
SCRIPT_PATTERNS = {
    "latin": re.compile(r"[a-zA-Z\u00C0-\u024F\u1E00-\u1EFF\u0100-\u017F\u0180-\u024F]"),
    "arabic": re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"),
    "cyrillic": re.compile(r"[\u0400-\u04FF\u0500-\u052F\u2DE0-\u2DFF\uA640-\uA69F]"),
    "devanagari": re.compile(r"[\u0900-\u097F\uA8E0-\uA8FF]"),
    "bengali": re.compile(r"[\u0980-\u09FF]"),
    "gurmukhi": re.compile(r"[\u0A00-\u0A7F]"),
    "gujarati": re.compile(r"[\u0A80-\u0AFF]"),
    "oriya": re.compile(r"[\u0B00-\u0B7F]"),
    "tamil": re.compile(r"[\u0B80-\u0BFF]"),
    "telugu": re.compile(r"[\u0C00-\u0C7F]"),
    "kannada": re.compile(r"[\u0C80-\u0CFF]"),
    "malayalam": re.compile(r"[\u0D00-\u0D7F]"),
    "sinhala": re.compile(r"[\u0D80-\u0DFF]"),
    "thai": re.compile(r"[\u0E00-\u0E7F]"),
    "lao": re.compile(r"[\u0E80-\u0EFF]"),
    "tibetan": re.compile(r"[\u0F00-\u0FFF]"),
    "myanmar": re.compile(r"[\u1000-\u109F\uAA60-\uAA7F]"),
    "georgian": re.compile(r"[\u10A0-\u10FF\u2D00-\u2D2F]"),
    "hangul": re.compile(r"[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]"),
    "cjk": re.compile(r"[\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF]"),
    "kana": re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u31F0-\u31FF]"),
    "hebrew": re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F]"),
    "armenian": re.compile(r"[\u0530-\u058F\uFB00-\uFB17]"),
    "ethiopic": re.compile(r"[\u1200-\u137F\u1380-\u139F\u2D80-\u2DDF]"),
    "khmer": re.compile(r"[\u1780-\u17FF\u19E0-\u19FF]"),
}

# Expected scripts per locale — comprehensive mapping covering all fastText languages.
# Languages may accept multiple scripts (e.g. Serbian uses both Cyrillic and Latin).
# fmt: off
LOCALE_SCRIPTS = {
    # Latin script
    "af": {"latin"}, "az": {"latin"}, "br": {"latin"}, "bs": {"latin"}, "ca": {"latin"},
    "ceb": {"latin"}, "co": {"latin"}, "cs": {"latin"}, "cy": {"latin"}, "da": {"latin"},
    "de": {"latin"}, "en": {"latin"}, "eo": {"latin"}, "es": {"latin"}, "et": {"latin"},
    "eu": {"latin"}, "fi": {"latin"}, "fil": {"latin"}, "fr": {"latin"}, "fy": {"latin"},
    "ga": {"latin"}, "gd": {"latin"}, "gl": {"latin"}, "ha": {"latin"}, "haw": {"latin"},
    "hr": {"latin"}, "ht": {"latin"}, "hu": {"latin"}, "id": {"latin"}, "ig": {"latin"},
    "is": {"latin"}, "it": {"latin"}, "jv": {"latin"}, "la": {"latin"}, "lb": {"latin"},
    "lt": {"latin"}, "lv": {"latin"}, "mg": {"latin"}, "mi": {"latin"}, "ms": {"latin"},
    "mt": {"latin"}, "nl": {"latin"}, "no": {"latin"}, "nb": {"latin"}, "nn": {"latin"},
    "ny": {"latin"}, "oc": {"latin"}, "pl": {"latin"}, "pt": {"latin"}, "ro": {"latin"},
    "rw": {"latin"}, "sk": {"latin"}, "sl": {"latin"}, "sm": {"latin"}, "sn": {"latin"},
    "so": {"latin"}, "sq": {"latin"}, "st": {"latin"}, "su": {"latin"}, "sv": {"latin"},
    "sw": {"latin"}, "tl": {"latin"}, "tr": {"latin"}, "uz": {"latin"}, "vi": {"latin"},
    "war": {"latin"}, "xh": {"latin"}, "yo": {"latin"}, "zu": {"latin"},
    # Cyrillic script
    "be": {"cyrillic"}, "bg": {"cyrillic"}, "ky": {"cyrillic"}, "kk": {"cyrillic"},
    "mk": {"cyrillic"}, "mn": {"cyrillic"}, "ru": {"cyrillic"}, "tg": {"cyrillic"},
    "tt": {"cyrillic"}, "uk": {"cyrillic"},
    # Multi-script languages
    "sr": {"cyrillic", "latin"}, "sh": {"cyrillic", "latin"},
    # Arabic script
    "ar": {"arabic"}, "fa": {"arabic"}, "ku": {"arabic"}, "ps": {"arabic"},
    "sd": {"arabic"}, "ug": {"arabic"}, "ur": {"arabic"},
    # Devanagari
    "hi": {"devanagari"}, "mr": {"devanagari"}, "ne": {"devanagari"}, "sa": {"devanagari"},
    # Other Indic scripts
    "as": {"bengali"}, "bn": {"bengali"},
    "gu": {"gujarati"},
    "kn": {"kannada"},
    "ml": {"malayalam"},
    "or": {"oriya"},
    "pa": {"gurmukhi"},
    "si": {"sinhala"},
    "ta": {"tamil"},
    "te": {"telugu"},
    # East Asian
    "zh": {"cjk"}, "zh_Hans": {"cjk"}, "zh_Hant": {"cjk"},
    "ja": {"cjk", "kana"},
    "ko": {"hangul"},
    # Other scripts
    "am": {"ethiopic"}, "ti": {"ethiopic"},
    "el": {"latin"},  # Greek — could add greek script pattern if needed
    "he": {"hebrew"}, "yi": {"hebrew"},
    "hy": {"armenian"},
    "ka": {"georgian"},
    "km": {"khmer"},
    "lo": {"lao"},
    "my": {"myanmar"},
    "th": {"thai"},
}
# fmt: on


def detect_scripts(text: str) -> dict[str, int]:
    """Count characters belonging to each script in the text."""
    counts = {}
    for name, pattern in SCRIPT_PATTERNS.items():
        count = len(pattern.findall(text))
        if count > 0:
            counts[name] = count
    return counts


def check_wrong_script(msgstr: str, locale: str) -> Issue | None:
    """Check if the translation uses the wrong writing script or wrong language within the same script.

    1. Entirely wrong script (e.g. Latin in Arabic file) → ERROR
    2. Distinctive character check for same-script languages (e.g. Russian chars in Ukrainian file) → ERROR
    """
    expected = LOCALE_SCRIPTS.get(locale)
    if not expected:
        return None

    scripts = detect_scripts(msgstr)
    if not scripts:
        return None

    # Check if any expected script is present
    expected_present = any(s in scripts for s in expected)

    # Find dominant script
    dominant = max(scripts, key=scripts.get)
    dominant_count = scripts[dominant]
    total = sum(scripts.values())

    if dominant in expected:
        # Script is correct — check distinctive characters for same-script languages
        return _check_distinctive_chars(msgstr, locale)

    # Wrong script is dominant
    if dominant_count / total < 0.5:
        return None

    # Expected script is present but not dominant — likely technical terms mixed in, ignore
    if expected_present:
        return None

    # Expected script is completely absent — clear contamination
    return Issue(
        file="",
        line=0,
        msgid="",
        msgstr=msgstr,
        issue_type=IssueType.WRONG_SCRIPT,
        severity=Severity.ERROR,
        message=f"Expected {'/'.join(expected)} script, found entirely {dominant} ({dominant_count}/{total} chars)",
    )


def _check_distinctive_chars(msgstr: str, locale: str) -> Issue | None:
    """Check for foreign distinctive characters within the same script.

    If foreign-only characters are found, it's contamination — regardless of
    whether the locale's own distinctive characters are also present.
    If no distinctive characters from either side are found, we can't tell — skip.
    """
    config = DISTINCTIVE_CHARS.get(locale)
    if not config:
        return None

    chars = set(msgstr)
    has_own = bool(chars & config["own"])

    for foreign_lang, foreign_chars in config.items():
        if foreign_lang == "own":
            continue
        has_foreign = bool(chars & foreign_chars)
        if not has_foreign:
            continue

        if has_own:
            message = f"Mixed {locale}/{foreign_lang} characters — possible contamination"
        else:
            message = f"Found {foreign_lang}-only characters, no {locale}-specific characters"

        return Issue(
            file="",
            line=0,
            msgid="",
            msgstr=msgstr,
            issue_type=IssueType.WRONG_SCRIPT,
            severity=Severity.ERROR,
            message=message,
        )

    return None



# Distinctive characters per locale — used to distinguish languages that share
# a script but have unique alphabet characters. Each entry maps a locale to its
# own unique characters and the foreign characters that indicate contamination.
# Add new entries as needed for other language pairs (e.g. Serbian/Bulgarian).
DISTINCTIVE_CHARS: dict[str, dict[str, set[str]]] = {
    "uk": {"own": set("ґєіїҐЄІЇ"), "ru": set("ёыэъЁЫЭЪ")},
    "ru": {"own": set("ёыэъЁЫЭЪ"), "uk": set("ґєіїҐЄІЇ")},
}


def check_shifted_entry(msgid: str, msgstr: str) -> Issue | None:
    """Detect entries where msgstr appears to be shifted (belongs to a different msgid).

    Heuristic: if msgid is long (>100 chars) but msgstr is very short (<15% of msgid length),
    the translation is likely shifted from a different entry.
    """
    if not msgstr or not msgid:
        return None

    msgid_len = len(msgid)
    msgstr_len = len(msgstr)

    if msgid_len < 100:
        return None

    ratio = msgstr_len / msgid_len
    if ratio >= 0.15:
        return None

    return Issue(
        file="",
        line=0,
        msgid=msgid,
        msgstr=msgstr,
        issue_type=IssueType.SHIFTED_ENTRY,
        severity=Severity.WARNING,
        message=f"Possible shifted entry: msgstr is {ratio:.0%} the length of msgid ({msgstr_len} vs {msgid_len} chars)",
    )


def check_garbled_text(msgstr: str) -> Issue | None:
    """Detect garbled/corrupted text patterns."""
    if len(msgstr) < 5:
        return None

    # Check for high ratio of replacement characters or unusual unicode categories
    suspicious = 0
    total = 0
    for char in msgstr:
        cat = unicodedata.category(char)
        total += 1
        if cat.startswith("C") and cat != "Cf":  # Control chars (except format)
            suspicious += 1
        elif char == "\ufffd":  # Replacement character
            suspicious += 1

    if total > 0 and suspicious / total > 0.1:
        return Issue(
            file="",
            line=0,
            msgid="",
            msgstr=msgstr,
            issue_type=IssueType.GARBLED_TEXT,
            severity=Severity.ERROR,
            message=f"Garbled text detected: {suspicious}/{total} suspicious characters",
        )

    return None
