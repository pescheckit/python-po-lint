# python-po-lint

Lint `.po` translation files for contamination, wrong languages, shifts, and garbled text.

## Features

- **Wrong script detection** — catches Cyrillic in a Dutch file, Arabic in French, etc.
- **Wrong language detection** — hybrid fastText + lingua approach (fastText for long strings, lingua for short ones)
- **Shifted entry detection** — finds translations that got shifted to the wrong msgid
- **Garbled text detection** — catches corrupted/broken unicode

## Installation

```bash
pip install python-po-lint
```

## Usage

```bash
# Lint a locale directory
po-lint locale/

# Lint with config from pyproject.toml
po-lint

# Only check specific languages
po-lint locale/ --languages fr de nl
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

# Minimum confidence to flag wrong language (0.0 - 1.0)
confidence_threshold = 0.5

# Skip entries with msgstr shorter than this
min_text_length = 3

# Regex patterns to ignore (matched against msgid and msgstr)
ignore_patterns = []
```
