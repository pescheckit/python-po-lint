"""Language detection using fastText for .po file linting."""

import os
import re
import urllib.request
from pathlib import Path

import fasttext

# Suppress fastText warnings about "\n" in input
fasttext.FastText.eprint = lambda x: None

# Default minimum cleaned text length to attempt language detection.
# Short strings are unreliable — loan words, cognates, and brand names
# make detection impossible for anything under ~30 characters.
DEFAULT_MIN_DETECTION_LENGTH = 30

FULL_MODEL_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin"
COMPACT_MODEL_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"
MODEL_DIR = Path(os.environ.get("PO_LINT_MODEL_DIR", Path.home() / ".cache" / "po-lint"))

# Common aliases: locale directory names that don't match the ISO 639-1 code
# used by fastText. Only edge cases go here — most codes work as-is.
LOCALE_ALIASES = {
    "zh_Hans": "zh",
    "zh_Hant": "zh",
    "zh_CN": "zh",
    "zh_TW": "zh",
    "nb": "no",       # Norwegian Bokmål → fastText uses "no"
    "nn": "no",       # Norwegian Nynorsk → fastText uses "no"
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

# Carrier phrases per language — used for second-pass confirmation.
# When fastText flags a wrong language, we re-test with a carrier phrase
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

# Confused language merges: when fastText detects a language that is commonly
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
    # Cyrillic languages — shared script and vocabulary
    "uk": {"ru"},
    "ru": {"uk"},
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


def _normalize_locale(locale: str) -> str:
    """Normalize a locale directory name to a fastText-compatible ISO code."""
    return LOCALE_ALIASES.get(locale, locale)


def _use_compact_model() -> bool:
    """Check if compact model is requested via environment variable."""
    return os.environ.get("PO_LINT_COMPACT_MODEL", "").lower() in ("1", "true", "yes")


def ensure_model(compact: bool = False) -> Path:
    """Download the fastText language ID model if not already cached."""
    if compact or _use_compact_model():
        url = COMPACT_MODEL_URL
        path = MODEL_DIR / "lid.176.ftz"
    else:
        url = FULL_MODEL_URL
        path = MODEL_DIR / "lid.176.bin"

    if path.exists():
        return path
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_type = "compact" if "ftz" in path.name else "full"
    print(f"Downloading fastText language model ({model_type}) to {path}...")
    urllib.request.urlretrieve(url, path)
    return path


_ft_model = None


def init_model(compact: bool = False) -> None:
    """Initialize the fastText model. Call before linting to select model variant."""
    global _ft_model
    model_path = ensure_model(compact)
    _ft_model = fasttext.load_model(str(model_path))


def get_ft_model() -> fasttext.FastText._FastText:
    """Load the fastText model (singleton). Auto-initializes with default if not yet loaded."""
    global _ft_model
    if _ft_model is None:
        init_model()
    return _ft_model


def clean_text(text: str) -> str:
    """Strip HTML tags, template tags, format strings, and URLs for better detection."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\{[%{].*?[%}]\}", " ", text)
    text = re.sub(r"%\([^)]+\)[sd]", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_language(text: str, min_detection_length: int = DEFAULT_MIN_DETECTION_LENGTH) -> tuple[str, float]:
    """Detect language of text using fastText.

    Returns (lang_code, confidence). Returns ("unknown", 0.0) for text
    shorter than min_detection_length after cleaning.
    """
    cleaned = clean_text(text)
    if len(cleaned) < min_detection_length:
        return ("unknown", 0.0)

    return _detect_fasttext(cleaned)


def _detect_fasttext(text: str, k: int = 1) -> tuple[str, float] | dict[str, float]:
    """Detect language using fastText.

    With k=1, returns (lang, confidence).
    With k>1, returns a dict of {lang: confidence} for the top-k predictions.
    """
    model = get_ft_model()
    predictions = model.predict(text.replace("\n", " "), k=k)
    if k == 1:
        label = predictions[0][0].replace("__label__", "")
        confidence = predictions[1][0]
        return (label, confidence)
    return {
        label.replace("__label__", ""): conf
        for label, conf in zip(predictions[0], predictions[1])
    }


def _merge_confused_scores(
    scores: dict[str, float], expected_code: str,
) -> dict[str, float]:
    """Merge scores from languages commonly confused with the expected language.

    When fastText splits its confidence between the expected language and
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

    # Get top-5 scores and merge confused language scores
    scores = _detect_fasttext(cleaned, k=5)
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
        boosted_scores = _detect_fasttext(f"{carrier} {cleaned}", k=5)
        boosted_det_conf = boosted_scores.get(detected_lang, 0.0)
        boosted_exp_conf = boosted_scores.get(expected_code, 0.0)

        if bare_det_conf > 0:
            det_drop = (bare_det_conf - boosted_det_conf) / bare_det_conf
            exp_rise = boosted_exp_conf - bare_exp_conf
            if det_drop > 0.60 and exp_rise > 0.20:
                return (False, detected_lang, confidence)

    return (True, detected_lang, confidence)
