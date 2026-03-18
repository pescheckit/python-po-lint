"""Configuration loading from pyproject.toml."""

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib


@dataclass
class Config:
    """po-lint configuration."""

    paths: list[Path] = field(default_factory=lambda: [Path("locale")])
    packages: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    source_language: str = "en"
    confidence_threshold: float = 0.5
    min_text_length: int = 3
    min_detection_length: int = 30
    ignore_patterns: list[str] = field(default_factory=list)
    compact_model: bool = False
    disable: list[str] = field(default_factory=list)

    def resolve_locale_dirs(self, base_dir: Path) -> list[Path]:
        """Resolve all locale directories from paths and packages.

        Returns a list of existing locale directories.
        """
        locale_dirs = []

        # Explicit paths (relative to base_dir)
        for p in self.paths:
            resolved = base_dir / p if not p.is_absolute() else p
            if resolved.is_dir():
                locale_dirs.append(resolved)

        # Auto-discover from installed packages
        for package_name in self.packages:
            locale_dir = find_package_locale(package_name)
            if locale_dir and locale_dir.is_dir():
                locale_dirs.append(locale_dir)

        return locale_dirs


def find_package_locale(package_name: str) -> Path | None:
    """Find the locale directory for an installed Python package."""
    spec = importlib.util.find_spec(package_name)
    if spec is None or spec.origin is None:
        return None
    package_dir = Path(spec.origin).parent
    locale_dir = package_dir / "locale"
    if locale_dir.is_dir():
        return locale_dir
    return None


def load_config(project_dir: Path | None = None) -> Config:
    """Load configuration from pyproject.toml in the given directory.

    Falls back to defaults if no config file or no [tool.po-lint] section found.
    """
    if project_dir is None:
        project_dir = Path.cwd()

    pyproject = project_dir / "pyproject.toml"
    if not pyproject.exists():
        return Config()

    with open(pyproject, "rb") as f:
        data = tomllib.load(f)

    tool_config = data.get("tool", {}).get("po-lint", {})
    if not tool_config:
        return Config()

    return Config(
        paths=[Path(p) for p in tool_config.get("paths", ["locale"])],
        packages=tool_config.get("packages", []),
        languages=tool_config.get("languages", []),
        source_language=tool_config.get("source_language", "en"),
        confidence_threshold=tool_config.get("confidence_threshold", 0.5),
        min_text_length=tool_config.get("min_text_length", 3),
        min_detection_length=tool_config.get("min_detection_length", 30),
        ignore_patterns=tool_config.get("ignore_patterns", []),
        compact_model=tool_config.get("compact_model", False),
        disable=tool_config.get("disable", []),
    )
