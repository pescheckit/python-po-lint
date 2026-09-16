# python-po-lint

Lint `.po` translation files for contamination, wrong languages, missing translations, shifts, and garbled text.

Uses [lingua](https://github.com/pemistahl/lingua-py) language identification with carrier phrase confirmation and confused language score merging for high accuracy with zero false positives.

## Features

- **Wrong language detection** — lingua-based, restricted to the languages in your catalogs, with a relative confidence rule and script filtering
- **Wrong script detection** — catches Cyrillic in a Dutch file, Arabic in French, Latin in Chinese, etc.
- **Distinctive character detection** — catches Russian-specific chars in Ukrainian and vice versa
- **Fuzzy entry detection** — flags entries with the fuzzy flag that need review
- **Obsolete entry detection** — flags obsolete entries that should be removed
- **Untranslated entry detection** — flags missing translations, auto-detects source language
- **Shifted entry detection** — finds translations that got shifted to the wrong msgid
- **Garbled text detection** — catches corrupted/broken unicode
- **Ignore rules** — `.po-lint-ignore` file with language scoping and msgctxt support
- **Configurable checks** — disable individual checks via `pyproject.toml` or CLI

## Installation

```bash
pip install python-po-lint
```

Or with uv:

```bash
uv add python-po-lint
```

Language models ship inside the lingua wheel; nothing is downloaded at runtime.

## Usage

```bash
# Lint a locale directory
po-lint locale/

# Lint with config from pyproject.toml
po-lint

# Only check specific languages
po-lint locale/ --languages fr de nl

# Use lingua's low accuracy mode (faster, less reliable on short text)
po-lint locale/ --compact-model

# JSON output
po-lint locale/ --format json

# Custom confidence threshold
po-lint locale/ --confidence 0.6

# Custom minimum detection length
po-lint locale/ --min-detection-length 25

# Specify source language (default: en)
po-lint locale/ --source-language en

# Disable specific checks
po-lint locale/ --disable untranslated fuzzy
```

## Configuration

Add to your `pyproject.toml`:

```toml
[tool.po-lint]
# Explicit locale directories (relative to project root)
paths = ["locale"]

# Auto-discover locale dirs from installed Python packages
packages = ["myapp", "myotherapp"]

# Only check these languages (empty = all)
languages = []

# Source language — detections matching this are allowed (borrowed words)
source_language = "en"

# Flag only when another language tops this confidence (0.0 - 1.0)
confidence_threshold = 0.7

# ...while the expected language's own confidence is below this
expected_confidence_max = 0.05

# Minimum cleaned text length for language detection
min_detection_length = 30

# Skip entries with msgstr shorter than this
min_text_length = 3

# Use lingua's low accuracy mode instead of the default high accuracy mode
compact_model = false

# Disable specific checks
# Valid: wrong_language, wrong_script, shifted_entry, garbled_text, untranslated, fuzzy, obsolete
disable = []

# Regex patterns to ignore (matched against msgid and msgstr)
ignore_patterns = []
```

## Ignore file

Create a `.po-lint-ignore` file in your locale directory:

```
# Ignore for all languages
Some msgid that causes false positives

# Ignore only for specific languages
[ar,hi] Some msgid

# Ignore with specific msgctxt
screening status::Some msgid

# Both language scope and context
[ar] screening status::Some msgid
```

## How it works

1. **Fuzzy entry check** — flags entries marked as fuzzy that need review.
2. **Obsolete entry check** — flags obsolete entries that should be removed.
3. **Untranslated entry check** — flags entries with empty `msgstr`. The source language is auto-detected (the locale where all entries are untranslated) or can be set explicitly. Skipped for the source language.
4. **Wrong script check** — fast, no model needed. Checks if the translation uses the expected writing system.
5. **Distinctive character check** — detects cross-contamination between languages sharing a script (e.g. Russian/Ukrainian).
6. **Garbled text check** — flags corrupted unicode.
7. **Shifted entry check** — flags suspiciously short translations for long source strings.
8. **Wrong language check** — uses lingua with three layers of false positive prevention:
   - **Restricted candidate set** — the detector only considers the languages present in the linted catalogs plus the source language, so text can't be attributed to exotic lookalikes
   - **Script filtering** — tokens in a script the locale doesn't use (quoted product names, brand terms) are stripped before detection instead of drowning out the native text
   - **Relative confidence rule** — flags only when the expected language scores below `expected_confidence_max` while another language tops `confidence_threshold`, i.e. the text is clearly NOT the expected language, not merely closer to a sibling

## License

MIT
