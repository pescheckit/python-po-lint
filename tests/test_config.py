"""Tests for configuration loading."""

from pathlib import Path

from po_lint.config import Config, load_config


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestConfig:
    def test_defaults(self):
        config = Config()
        assert config.paths == [Path("locale")]
        assert config.packages == []
        assert config.confidence_threshold == 0.5

    def test_resolve_locale_dirs(self):
        config = Config(paths=[Path("locale")])
        dirs = config.resolve_locale_dirs(FIXTURES_DIR)
        assert len(dirs) == 1
        assert dirs[0] == FIXTURES_DIR / "locale"

    def test_resolve_nonexistent_path(self):
        config = Config(paths=[Path("nonexistent")])
        dirs = config.resolve_locale_dirs(FIXTURES_DIR)
        assert len(dirs) == 0

    def test_resolve_packages(self):
        config = Config(paths=[], packages=["polib"])
        dirs = config.resolve_locale_dirs(FIXTURES_DIR)
        # polib doesn't have a locale dir, so it shouldn't be found
        assert len(dirs) == 0


class TestLoadConfig:
    def test_no_pyproject(self, tmp_path):
        config = load_config(tmp_path)
        assert config.paths == [Path("locale")]

    def test_pyproject_without_tool_section(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        config = load_config(tmp_path)
        assert config.paths == [Path("locale")]

    def test_pyproject_with_config(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.po-lint]\n'
            'paths = ["translations", "other/locale"]\n'
            'packages = ["myapp"]\n'
            'confidence_threshold = 0.7\n'
            'min_text_length = 5\n'
            'ignore_patterns = ["^TODO"]\n'
        )
        config = load_config(tmp_path)
        assert config.paths == [Path("translations"), Path("other/locale")]
        assert config.packages == ["myapp"]
        assert config.confidence_threshold == 0.7
        assert config.min_text_length == 5
        assert config.ignore_patterns == ["^TODO"]
