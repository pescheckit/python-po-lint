"""Language detection using lingua for .po file linting.

The detector is restricted to the languages that can actually occur in the
linted catalogs: the locales present plus the source language. Contamination
realistically comes from a neighbouring row of the same translation batch, and
restricting the candidate set keeps lingua's confidence mass on languages we
can act on instead of exotic lookalikes (Ukrainian scoring as Kazakh, English
tech terms scoring as Tagalog).

A translation is flagged through a relative rule on lingua's full confidence
distribution: the expected language must score below ``expected_confidence_max``
while another language tops ``confidence_threshold``. This asks "is this text
clearly NOT the expected language" rather than "what is the argmax", which is
what keeps correct translations with foreign loan words from flagging.
"""

import os
import re

from lingua import IsoCode639_1, Language, LanguageDetectorBuilder

from po_lint.checks import LOCALE_SCRIPTS, SCRIPT_PATTERNS

# Default minimum cleaned text length to attempt language detection.
# Short strings are unreliable — loan words, cognates, and brand names
# make detection impossible for anything under ~30 characters.
DEFAULT_MIN_DETECTION_LENGTH = 30

# Flag only when another language tops this confidence...
DEFAULT_TOP_CONFIDENCE_MIN = 0.7
# ...while the expected language scores below this.
DEFAULT_EXPECTED_CONFIDENCE_MAX = 0.05

# Common aliases: locale directory names that don't match the ISO 639-1 code
# used internally. Only edge cases go here — most codes work as-is.
LOCALE_ALIASES = {
    "zh_Hans": "zh",
    "zh_Hant": "zh",
    "zh_CN": "zh",
    "zh_TW": "zh",
    "nb": "no",       # Norwegian Bokmål → folded into macrolanguage "no"
    "nn": "no",       # Norwegian Nynorsk → folded into macrolanguage "no"
    "pt_BR": "pt",
    "pt_PT": "pt",
    "es_AR": "es",
    "es_MX": "es",
    "en_US": "en",
    "en_GB": "en",
    "fr_CA": "fr",
    "fr_FR": "fr",
    "sr_Latn": "sr",
    "sr_Cyrl": "sr",
}

# lingua distinguishes Bokmål and Nynorsk but has no Norwegian macrolanguage,
# while locale directories use "no". Fold both into "no" on the detection side
# so expected and detected codes live in the same space.
_DETECTED_FOLDS = {"nb": "no", "nn": "no"}


def _normalize_locale(locale: str) -> str:
    """Normalize a locale directory name to a detector-compatible ISO code."""
    return LOCALE_ALIASES.get(locale, locale)


def _languages_for(code: str) -> list[Language]:
    """Map a normalized locale code to lingua Language members ([] if unsupported)."""
    if code == "no":
        return [Language.BOKMAL, Language.NYNORSK]
    # lingua's enums are PyO3 types: not subscriptable, members are attributes
    iso = getattr(IsoCode639_1, code.upper(), None) if code.isalpha() else None
    if iso is None:
        return []
    try:
        return [Language.from_iso_code_639_1(iso)]
    except ValueError:
        return []


def _use_low_accuracy_mode() -> bool:
    """Check if low accuracy mode is requested via environment variable."""
    return os.environ.get("PO_LINT_COMPACT_MODEL", "").lower() in ("1", "true", "yes")


_detector = None
_detector_codes: frozenset[str] | None = None  # None = all spoken languages
_low_accuracy = False


def init_model(languages=None, compact: bool = False) -> None:
    """Initialize the lingua detector.

    ``languages`` is an iterable of locale codes to restrict detection to
    (unsupported codes are dropped); None builds from all spoken languages.
    ``compact`` maps to lingua's low accuracy mode: smaller models, faster,
    less reliable on short text.
    """
    global _detector, _detector_codes, _low_accuracy
    _low_accuracy = compact or _use_low_accuracy_mode()

    if languages is None:
        _detector_codes = None
        builder = LanguageDetectorBuilder.from_all_spoken_languages()
    else:
        codes = {_normalize_locale(c) for c in languages}
        codes = {c for c in codes if _languages_for(c)}
        langs = {lang for c in codes for lang in _languages_for(c)}
        if len(langs) < 2:
            # lingua needs at least two candidate languages to compare
            _detector_codes = None
            builder = LanguageDetectorBuilder.from_all_spoken_languages()
        else:
            _detector_codes = frozenset(codes)
            builder = LanguageDetectorBuilder.from_languages(*sorted(langs, key=lambda lg: lg.name))
    if _low_accuracy:
        builder = builder.with_low_accuracy_mode()
    _detector = builder.with_preloaded_language_models().build()


def ensure_languages(locales, source_language: str = "en") -> None:
    """Make sure the detector covers these locale codes, extending it if needed.

    Never shrinks the candidate set; an all-spoken detector stays all-spoken.
    """
    wanted = {_normalize_locale(c) for c in [*locales, source_language] if c}
    wanted = {c for c in wanted if _languages_for(c)}
    if _detector is not None and (_detector_codes is None or wanted <= _detector_codes):
        return
    if _detector is None:
        init_model(languages=wanted, compact=_low_accuracy)
    else:
        init_model(languages=set(_detector_codes) | wanted, compact=_low_accuracy)


def _get_detector():
    """Return the lingua detector, auto-initializing from all spoken languages."""
    global _detector
    if _detector is None:
        init_model()
    return _detector


def clean_text(text: str) -> str:
    """Strip HTML tags, template tags, format strings, and URLs for better detection."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\{[%{].*?[%}]\}", " ", text)
    text = re.sub(r"%\([^)]+\)[sd]", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _script_filter(text: str, expected_lang: str, expected_code: str) -> str:
    """Drop tokens written in a script the expected locale doesn't use.

    Product nouns quoted verbatim ("Скопіюйте Application ID та Client Secret")
    otherwise dominate detection: lingua only considers the majority script's
    words, so the native-language part never competes. All-foreign-script
    contamination is not lost to this — check_wrong_script catches it first.
    """
    expected_scripts = LOCALE_SCRIPTS.get(expected_lang) or LOCALE_SCRIPTS.get(expected_code)
    if not expected_scripts:
        return text
    patterns = [SCRIPT_PATTERNS[s] for s in expected_scripts if s in SCRIPT_PATTERNS]
    if not patterns:
        return text

    kept = []
    for token in text.split():
        letters = [ch for ch in token if ch.isalpha()]
        if not letters:
            kept.append(token)
            continue
        matching = sum(1 for ch in letters if any(p.match(ch) for p in patterns))
        if matching >= len(letters) / 2:
            kept.append(token)
    return " ".join(kept)


def _detect_scores(text: str) -> dict[str, float]:
    """Return the detector's confidence distribution as {lang_code: confidence}.

    Bokmål and Nynorsk confidences are folded into "no", so the mass of both
    variants counts toward the Norwegian macrolanguage.
    """
    scores: dict[str, float] = {}
    for entry in _get_detector().compute_language_confidence_values(text):
        code = entry.language.iso_code_639_1.name.lower()
        code = _DETECTED_FOLDS.get(code, code)
        scores[code] = scores.get(code, 0.0) + entry.value
    return scores


def detect_language(text: str, min_detection_length: int = DEFAULT_MIN_DETECTION_LENGTH) -> tuple[str, float]:
    """Detect language of text using lingua.

    Returns (lang_code, confidence). Returns ("unknown", 0.0) for text
    shorter than min_detection_length after cleaning.
    """
    cleaned = clean_text(text)
    if len(cleaned) < min_detection_length:
        return ("unknown", 0.0)

    scores = _detect_scores(cleaned)
    if not scores:
        return ("unknown", 0.0)
    detected = max(scores, key=scores.get)
    return (detected, scores[detected])


def is_wrong_language(
    msgstr: str,
    expected_lang: str,
    confidence_threshold: float = DEFAULT_TOP_CONFIDENCE_MIN,
    source_language: str = "en",
    msgid: str = "",
    min_detection_length: int = DEFAULT_MIN_DETECTION_LENGTH,
    expected_confidence_max: float = DEFAULT_EXPECTED_CONFIDENCE_MAX,
) -> tuple[bool, str, float]:
    """Check if a translation is in the wrong language.

    Only checks strings >= min_detection_length characters after cleaning and
    script filtering. Shorter strings are too ambiguous for reliable detection.

    Args:
        msgstr: The translated text to check.
        expected_lang: The locale code this translation should be in.
        confidence_threshold: Minimum top-language confidence to flag.
        source_language: The source language of the .po file (default: "en").
            Detections matching the source language are allowed, since borrowed
            words from the source language are common in translations.
        msgid: The source text (currently unused, reserved for future use).
        min_detection_length: Minimum cleaned text length to attempt detection.
        expected_confidence_max: Flag only if the expected language's own
            confidence falls below this.

    Returns (is_wrong, detected_lang, confidence).
    """
    cleaned = clean_text(msgstr)
    if len(cleaned) < min_detection_length:
        return (False, "unknown", 0.0)

    expected_code = _normalize_locale(expected_lang)
    if not _languages_for(expected_code):
        # A locale lingua has no model for can never match itself — skip
        # rather than flag every entry.
        return (False, "unknown", 0.0)
    ensure_languages([expected_code], source_language)

    filtered = _script_filter(cleaned, expected_lang, expected_code)
    if len(filtered) < min_detection_length:
        return (False, "unknown", 0.0)

    scores = _detect_scores(filtered)
    if not scores:
        return (False, "unknown", 0.0)

    detected_lang = max(scores, key=scores.get)
    confidence = scores[detected_lang]
    expected_conf = scores.get(expected_code, 0.0)

    if detected_lang == expected_code:
        return (False, detected_lang, confidence)

    # Allow source language — borrowed words are common
    source_code = _normalize_locale(source_language)
    if detected_lang == source_code:
        return (False, detected_lang, confidence)

    if expected_conf < expected_confidence_max and confidence > confidence_threshold:
        return (True, detected_lang, confidence)

    return (False, detected_lang, confidence)
