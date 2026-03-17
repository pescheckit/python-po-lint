# python-po-lint

Lint `.po` translation files for contamination, wrong languages, missing translations, shifts, and garbled text.

Uses [fastText](https://fasttext.cc/) language identification with carrier phrase confirmation and confused language score merging for high accuracy with zero false positives.

## Features

- **Wrong language detection** — fastText-based with top-5 scoring, confused language merging, and carrier phrase confirmation
- **Wrong script detection** — catches Cyrillic in a Dutch file, Arabic in French, Latin in Chinese, etc.
- **Distinctive character detection** — catches Russian-specific chars in Ukrainian and vice versa
- **Untranslated entry detection** — flags missing translations, auto-detects source language
- **Shifted entry detection** — finds translations that got shifted to the wrong msgid
- **Garbled text detection** — catches corrupted/broken unicode
- **Ignore rules** — `.po-lint-ignore` file with language scoping and msgctxt support

## Installation

```bash
pip install python-po-lint
```

Or with uv:

```bash
uv add python-po-lint
```

The fastText language model (~126MB) is downloaded automatically on first run to `~/.cache/po-lint/`.

## Usage

```bash
# Lint a locale directory
po-lint locale/

# Lint with config from pyproject.toml
po-lint

# Only check specific languages
po-lint locale/ --languages fr de nl

# Use compact model (917KB, less accurate)
po-lint locale/ --compact-model

# JSON output
po-lint locale/ --format json

# Custom confidence threshold
po-lint locale/ --confidence 0.6

# Custom minimum detection length
po-lint locale/ --min-detection-length 25

# Specify source language (default: en)
po-lint locale/ --source-language en

# Disable untranslated entry check
po-lint locale/ --no-check-untranslated
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

# Minimum confidence to flag wrong language (0.0 - 1.0)
confidence_threshold = 0.5

# Minimum cleaned text length for language detection
min_detection_length = 30

# Skip entries with msgstr shorter than this
min_text_length = 3

# Use compact fastText model instead of full
compact_model = false

# Check for untranslated entries (default: true)
# Source language is auto-detected or set via source_language
check_untranslated = true

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

1. **Wrong script check** — fast, no model needed. Checks if the translation uses the expected writing system.
2. **Distinctive character check** — detects cross-contamination between languages sharing a script (e.g. Russian/Ukrainian).
3. **Garbled text check** — flags corrupted unicode.
4. **Untranslated entry check** — flags entries with empty `msgstr`. The source language is auto-detected (the locale where all entries are untranslated) or can be set explicitly. Skipped for the source language.
5. **Shifted entry check** — flags suspiciously short translations for long source strings.
6. **Wrong language check** — uses fastText with three layers of false positive prevention:
   - **Confused language score merging** — redistributes scores from commonly confused languages (e.g. Danish/Norwegian, Portuguese/Spanish)
   - **Source language allowance** — borrowed words from the source language are common and allowed
   - **Carrier phrase confirmation** — re-tests with a language-specific phrase prepended to distinguish false positives from real contamination

## License

MIT
