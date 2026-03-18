"""CLI entry point for po-lint."""

import argparse
import json
import sys
from pathlib import Path

from po_lint.checks import Severity
from po_lint.config import load_config
from po_lint.detector import init_model
from po_lint.linter import lint_locale_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="po-lint",
        description="Lint .po translation files for contamination, wrong languages, shifts, and garbled text. "
                    "Place a .po-lint-ignore file in the locale/ directory to suppress false positives.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Locale directories to lint. If omitted, reads from pyproject.toml [tool.po-lint] config.",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Directory containing pyproject.toml (default: current directory).",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=None,
        help="Minimum confidence threshold for wrong language detection (default: 0.5).",
    )
    parser.add_argument(
        "--languages",
        nargs="*",
        default=None,
        help="Only check these language codes (e.g. --languages fr de nl).",
    )
    parser.add_argument(
        "--source-language",
        default=None,
        help="Source language of the .po files (default: 'en'). Detections matching this language are allowed.",
    )
    parser.add_argument(
        "--min-detection-length",
        type=int,
        default=None,
        help="Minimum cleaned text length for language detection (default: 30).",
    )
    parser.add_argument(
        "--disable",
        nargs="*",
        default=None,
        help="Disable specific checks (e.g. --disable untranslated fuzzy). "
             "Valid checks: wrong_language, wrong_script, shifted_entry, garbled_text, untranslated, fuzzy, obsolete.",
    )
    parser.add_argument(
        "--compact-model",
        action="store_true",
        help="Use the compact fastText model (917KB, less accurate) instead of the full model (126MB).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="Treat warnings as errors (exit code 1).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output.",
    )
    args = parser.parse_args(argv)

    # Load config from pyproject.toml
    config_dir = args.config_dir or Path.cwd()
    config = load_config(config_dir)

    # CLI args override config
    confidence = args.confidence if args.confidence is not None else config.confidence_threshold
    languages = args.languages if args.languages is not None else (config.languages or None)
    source_language = args.source_language if args.source_language is not None else config.source_language
    min_detection_length = (
        args.min_detection_length if args.min_detection_length is not None
        else config.min_detection_length
    )
    disable = args.disable if args.disable is not None else config.disable

    # Resolve locale directories
    if args.paths:
        locale_dirs = [p for p in args.paths if p.is_dir()]
        if not locale_dirs:
            print(f"Error: No valid directories found in {args.paths}", file=sys.stderr)
            return 2
    else:
        locale_dirs = config.resolve_locale_dirs(config_dir)
        if not locale_dirs:
            print("Error: No locale directories found. Specify paths or configure [tool.po-lint] in pyproject.toml.",
                  file=sys.stderr)
            return 2

    # Initialize model
    compact = args.compact_model or config.compact_model
    init_model(compact=compact)

    # Run linting
    all_issues = []
    for locale_dir in locale_dirs:
        if args.format == "text":
            print(f"Linting {locale_dir}...")
        issues = lint_locale_dir(
            locale_dir,
            languages=languages,
            source_language=source_language,
            confidence_threshold=confidence,
            min_text_length=config.min_text_length,
            min_detection_length=min_detection_length,
            ignore_patterns=config.ignore_patterns,
            disable=disable,
        )
        all_issues.extend(issues)

    if args.format == "json":
        return _output_json(all_issues, args.warnings_as_errors)

    return _output_text(all_issues, args)


def _output_json(issues, warnings_as_errors: bool) -> int:
    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]

    output = {
        "summary": {
            "errors": len(errors),
            "warnings": len(warnings),
            "files": len({i.file for i in issues}),
        },
        "issues": [
            {
                "file": i.file,
                "line": i.line,
                "severity": i.severity.value,
                "type": i.issue_type.value,
                "message": i.message,
                "msgid": i.msgid,
                "msgstr": i.msgstr,
                "detected_lang": i.detected_lang or None,
                "confidence": round(i.confidence, 4) if i.confidence else None,
            }
            for i in sorted(issues, key=lambda x: (x.file, x.line))
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if errors:
        return 1
    if warnings and warnings_as_errors:
        return 1
    return 0


def _output_text(issues, args) -> int:
    if not issues:
        return 0

    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]

    by_file: dict[str, list] = {}
    for issue in issues:
        by_file.setdefault(issue.file, []).append(issue)

    use_color = not args.no_color and sys.stdout.isatty()

    for file_path, file_issues in sorted(by_file.items()):
        if use_color:
            print(f"\n\033[1m{file_path}\033[0m")
        else:
            print(f"\n{file_path}")

        for issue in sorted(file_issues, key=lambda i: i.line):
            prefix = _severity_prefix(issue.severity, use_color)
            msgid_short = issue.msgid[:60] + "..." if len(issue.msgid) > 60 else issue.msgid
            msgstr_short = issue.msgstr[:60] + "..." if len(issue.msgstr) > 60 else issue.msgstr
            print(f"  line {issue.line}: {prefix} [{issue.issue_type.value}] {issue.message}")
            if msgid_short:
                print(f"    msgid:  {msgid_short!r}")
            if msgstr_short:
                print(f"    msgstr: {msgstr_short!r}")

    print(f"\nFound {len(errors)} error(s) and {len(warnings)} warning(s) in {len(by_file)} file(s).")

    if errors:
        return 1
    if warnings and args.warnings_as_errors:
        return 1
    return 0


def _severity_prefix(severity: Severity, color: bool) -> str:
    if severity == Severity.ERROR:
        return "\033[31mERROR\033[0m" if color else "ERROR"
    return "\033[33mWARNING\033[0m" if color else "WARNING"


if __name__ == "__main__":
    sys.exit(main())
