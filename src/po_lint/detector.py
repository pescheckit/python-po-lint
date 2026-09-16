"""Language detection using lingua for .po file linting."""

import os
import re

from lingua import Language, LanguageDetectorBuilder

# Default minimum cleaned text length to attempt language detection.
# Short strings are unreliable — loan words, cognates, and brand names
# make detection impossible for anything under ~30 characters.
DEFAULT_MIN_DETECTION_LENGTH = 30

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

# Carrier phrases per language — used for second-pass confirmation.
# When the detector flags a wrong language, we re-test with a carrier phrase
# prepended. If the originally detected language drops significantly (>60%)
# and the expected language rises significantly (>20%), the original detection
# was likely a false positive on ambiguous text.
# Uses short "context" style phrases ("In X one says") to give just enough
# signal without overpowering real contamination in related languages.
CARRIER_PHRASES = {
    "af": "In Afrikaans sê mens",
    "ar": "بالعربية يقال",
    "bg": "На български се казва",
    "bn": "বাংলায় বলা হয়",
    "bs": "Na bosanskom se kaže",
    "ca": "En català es diu",
    "cs": "Česky se říká",
    "da": "På dansk siger man",
    "de": "Auf Deutsch sagt man",
    "el": "Στα ελληνικά λέμε",
    "en": "In English one says",
    "es": "En español se dice",
    "et": "Eesti keeles öeldakse",
    "fa": "به فارسی می‌گویند",
    "fi": "Suomeksi sanotaan",
    "fr": "En français on dit",
    "he": "בעברית אומרים",
    "hi": "हिंदी में कहते हैं",
    "hr": "Na hrvatskom se kaže",
    "hu": "Magyarul azt mondják",
    "id": "Dalam bahasa Indonesia dikatakan",
    "it": "In italiano si dice",
    "ja": "日本語では",
    "ko": "한국어로는",
    "lt": "Lietuviškai sakoma",
    "lv": "Latviski saka",
    "mk": "На македонски се вели",
    "ms": "Dalam bahasa Melayu dikatakan",
    "nl": "In het Nederlands zegt men",
    "no": "På norsk sier man",
    "pl": "Po polsku mówi się",
    "pt": "Em português diz-se",
    "ro": "În română se spune",
    "ru": "По-русски говорят",
    "sk": "Po slovensky sa hovorí",
    "sl": "V slovenščini se reče",
    "sr": "На српском се каже",
    "sv": "På svenska säger man",
    "sw": "Kwa Kiswahili tunasema",
    "th": "ในภาษาไทยพูดว่า",
    "tr": "Türkçede denir ki",
    "uk": "Українською кажуть",
    "vi": "Trong tiếng Việt người ta nói",
    "zh": "用中文来说",
}

# Confused language merges: when the detector reports a language that is commonly
# confused with the expected language, merge its score into the expected language's
# score. This is directional — e.g. Swedish text can be confused as German (sv merges
# de), but German text is rarely confused as Swedish (de does NOT merge sv).
# This replaces blanket skipping with score redistribution, so genuinely wrong
# translations at very high confidence are still caught.
CONFUSED_MERGES: dict[str, set[str]] = {
    # Scandinavian languages — very similar vocabulary and grammar
    "no": {"da", "sv", "nb", "nn", "de"},
    "da": {"no", "sv", "nb", "nn", "de"},
    "sv": {"no", "da", "nb", "nn", "de"},
    "nb": {"no", "da", "sv", "nn", "de"},
    "nn": {"no", "da", "sv", "nb", "de"},
    # Romance languages
    "pt": {"es", "gl"},
    "es": {"pt", "gl"},
    "gl": {"pt", "es"},
    # Germanic
    "nl": {"af"},
    "af": {"nl"},
    # Turkic languages
    "tr": {"az"},
    "az": {"tr"},
    # Cyrillic languages — shared script and vocabulary. Ukrainian text with
    # dotted і reads as Kazakh to lingua (Kazakh Cyrillic also has і), and
    # short Russian phrases read as Bulgarian; both merges are directional.
    "uk": {"ru", "kk"},
    "ru": {"uk", "bg"},
    "bg": {"mk"},
    "mk": {"bg"},
    # Indic languages — shared Devanagari script
    "hi": {"mr"},
    "mr": {"hi"},
    # Arabic script languages — shared script and vocabulary roots
    "ar": {"fa", "ur"},
    "fa": {"ar", "ur"},
    "ur": {"ar", "fa"},
}


def _lang_code(language: Language) -> str:
    code = language.iso_code_639_1.name.lower()
    return _DETECTED_FOLDS.get(code, code)


SUPPORTED_CODES = frozenset(_lang_code(lang) for lang in Language.all_spoken_ones())


def _normalize_locale(locale: str) -> str:
    """Normalize a locale directory name to a detector-compatible ISO code."""
    return LOCALE_ALIASES.get(locale, locale)


def _use_low_accuracy_mode() -> bool:
    """Check if low accuracy mode is requested via environment variable."""
    return os.environ.get("PO_LINT_COMPACT_MODEL", "").lower() in ("1", "true", "yes")


_detector = None


def init_model(compact: bool = False) -> None:
    """Initialize the lingua detector. Call before linting to select the accuracy mode.

    ``compact`` maps to lingua's low accuracy mode: smaller models, faster,
    less reliable on short text.
    """
    global _detector
    builder = LanguageDetectorBuilder.from_all_spoken_languages()
    if compact or _use_low_accuracy_mode():
        builder = builder.with_low_accuracy_mode()
    _detector = builder.with_preloaded_language_models().build()


def _get_detector():
    """Return the lingua detector (singleton). Auto-initializes with defaults if not yet loaded."""
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


def _detect_scores(text: str) -> dict[str, float]:
    """Return the detector's confidence distribution as {lang_code: confidence}.

    Bokmål and Nynorsk confidences are folded into "no", so the mass of both
    variants counts toward the Norwegian macrolanguage.
    """
    scores: dict[str, float] = {}
    for entry in _get_detector().compute_language_confidence_values(text):
        code = _lang_code(entry.language)
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


def _merge_confused_scores(
    scores: dict[str, float], expected_code: str,
) -> dict[str, float]:
    """Merge scores from languages commonly confused with the expected language.

    When the detector splits its confidence between the expected language and
    languages it commonly confuses with it, this merges those scores together.
    For example, Swedish text might get de:63% + sv:12% — if sv has de in its
    merge set, the adjusted score becomes sv:75%.
    """
    merge_from = CONFUSED_MERGES.get(expected_code)
    if not merge_from:
        return scores
    adjusted = dict(scores)
    bonus = sum(scores.get(lang, 0.0) for lang in merge_from)
    adjusted[expected_code] = adjusted.get(expected_code, 0.0) + bonus
    for lang in merge_from:
        adjusted.pop(lang, None)
    return adjusted


def is_wrong_language(
    msgstr: str,
    expected_lang: str,
    confidence_threshold: float = 0.5,
    source_language: str = "en",
    msgid: str = "",
    min_detection_length: int = DEFAULT_MIN_DETECTION_LENGTH,
) -> tuple[bool, str, float]:
    """Check if a translation is in the wrong language.

    Only checks strings >= min_detection_length characters after cleaning.
    Shorter strings are too ambiguous for reliable detection.

    Args:
        msgstr: The translated text to check.
        expected_lang: The locale code this translation should be in.
        confidence_threshold: Minimum confidence to flag a wrong language.
        source_language: The source language of the .po file (default: "en").
            Detections matching the source language are allowed, since borrowed
            words from the source language are common in translations.
        msgid: The source text (currently unused, reserved for future use).
        min_detection_length: Minimum cleaned text length to attempt detection.

    Returns (is_wrong, detected_lang, confidence).
    """
    cleaned = clean_text(msgstr)
    if len(cleaned) < min_detection_length:
        return (False, "unknown", 0.0)

    expected_code = _normalize_locale(expected_lang)

    # A locale lingua has no model for can never match itself — skip rather
    # than flag every entry.
    if expected_code not in SUPPORTED_CODES:
        return (False, "unknown", 0.0)

    scores = _detect_scores(cleaned)
    adjusted = _merge_confused_scores(scores, expected_code)
    detected_lang = max(adjusted, key=adjusted.get)
    confidence = scores.get(detected_lang, adjusted[detected_lang])

    if detected_lang == "unknown":
        return (False, detected_lang, confidence)

    if detected_lang == expected_code:
        return (False, detected_lang, adjusted[detected_lang])

    # Allow source language — borrowed words are common
    source_code = _normalize_locale(source_language)
    if detected_lang == source_code:
        return (False, detected_lang, confidence)

    # Below confidence threshold — not certain enough to flag
    if confidence < confidence_threshold:
        return (False, detected_lang, confidence)

    # Second-pass confirmation with carrier phrase.
    # Re-test with a short phrase in the expected language prepended.
    # Compare how the detected language's confidence changes:
    # - Real contamination holds strong (detected lang barely drops)
    # - False positives crumble (detected lang drops >60%, expected rises >20%)
    carrier = CARRIER_PHRASES.get(expected_code)
    if carrier:
        bare_det_conf = scores.get(detected_lang, 0.0)
        bare_exp_conf = scores.get(expected_code, 0.0)
        boosted_scores = _detect_scores(f"{carrier} {cleaned}")
        boosted_det_conf = boosted_scores.get(detected_lang, 0.0)
        boosted_exp_conf = boosted_scores.get(expected_code, 0.0)

        if bare_det_conf > 0:
            det_drop = (bare_det_conf - boosted_det_conf) / bare_det_conf
            exp_rise = boosted_exp_conf - bare_exp_conf
            if det_drop > 0.60 and exp_rise > 0.20:
                return (False, detected_lang, confidence)

    return (True, detected_lang, confidence)
