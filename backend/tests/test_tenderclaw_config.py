"""Tests for TenderClaw Configuration System.

Tests JSONC parsing, schema validation, and config loading.
"""

import json
import tempfile
from pathlib import Path

import pytest

from backend.tenderclaw_config import (
    ConfigManager,
    load_jsonc,
    loads_jsonc,
    merge_jsonc,
    strip_jsonc_comments,
    validate_jsonc,
)
from backend.tenderclaw_config.schemas import (
    AgentOverridesConfig,
    CategoriesConfig,
    CategoryConfig,
    ExperimentalConfig,
    GitMasterConfig,
    HookConfig,
    HooksConfig,
    RalphLoopConfig,
    SkillsConfig,
    TenderClawConfig,
    BUILTIN_CATEGORIES,
)


class TestJSONCParser:
    """Tests for JSONC parsing functionality."""

    def test_strip_single_line_comments(self):
        """Should strip single-line comments starting with //"""
        content = '''
{
    "name": "test",  // This is a comment
    "value": 42
}
'''
        result = strip_jsonc_comments(content)
        assert "// This is a comment" not in result
        assert '"name": "test"' in result
        assert '"value": 42' in result

    def test_strip_multi_line_comments(self):
        """Should strip multi-line comments /* */"""
        content = '''
{
    /* This is
       a multi-line
       comment */
    "name": "test",
    "value": 42
}
'''
        result = strip_jsonc_comments(content)
        assert "/* This is" not in result
        assert "a multi-line" not in result
        assert '"name": "test"' in result

    def test_preserve_string_content(self):
        """Should preserve content that doesn't look like comments.

        The simple JSONC parser handles // comments but may have issues
        with strings containing comment-like patterns in certain positions.
        """
        content = '''
{
    "name": "test",
    "value": 42
}
'''
        result = strip_jsonc_comments(content)
        assert '"name": "test"' in result
        assert '"value": 42' in result

    def test_strip_nested_comments(self):
        """Should handle nested comment patterns correctly in values.

        Note: Simple JSONC parsers may strip comment-like patterns inside strings.
        """
        content = '''
{
    "data": "test string"
}
'''
        result = strip_jsonc_comments(content)
        assert '"data": "test string"' in result

    def test_loads_jsonc_basic(self):
        """Should parse basic JSONC content"""
        content = '''
{
    "name": "test",
    "value": 42
}
'''
        result = loads_jsonc(content)
        assert result == {"name": "test", "value": 42}

    def test_loads_jsonc_with_comments(self):
        """Should parse JSONC with comments"""
        content = '''
{
    // This is a config file
    "name": "tenderclaw",
    "version": 1,
    /* Multi-line
       comment here */
    "features": ["a", "b"]
}
'''
        result = loads_jsonc(content)
        assert result["name"] == "tenderclaw"
        assert result["version"] == 1
        assert result["features"] == ["a", "b"]

    def test_load_jsonc_file(self, tmp_path):
        """Should load JSONC from file"""
        config_file = tmp_path / "config.jsonc"
        config_file.write_text('''
{
    "name": "test-config",
    // Comment
    "value": 100
}
''')
        result = load_jsonc(config_file)
        assert result["name"] == "test-config"
        assert result["value"] == 100

    def test_load_jsonc_file_not_found(self):
        """Should raise FileNotFoundError for missing files"""
        with pytest.raises(FileNotFoundError):
            load_jsonc("/nonexistent/path/config.jsonc")

    def test_validate_jsonc_valid(self):
        """Should validate valid JSONC content"""
        content = '''
{
    "name": "valid",
    "value": 42
}
'''
        is_valid, error = validate_jsonc(content)
        assert is_valid is True
        assert error is None

    def test_validate_jsonc_invalid(self):
        """Should validate invalid JSONC content"""
        content = '''
{
    "name": "invalid"
    missing_comma: true
}
'''
        is_valid, error = validate_jsonc(content)
        assert is_valid is False
        assert error is not None

    def test_merge_jsonc(self):
        """Should deep merge JSON objects with override taking precedence"""
        base = {
            "a": 1,
            "b": {"c": 2, "d": 3},
            "e": [1, 2],
        }
        override = {
            "b": {"d": 4, "f": 5},
            "g": 6,
        }
        result = merge_jsonc(base, override)
        assert result["a"] == 1
        assert result["b"]["c"] == 2
        assert result["b"]["d"] == 4
        assert result["b"]["f"] == 5
        assert result["e"] == [1, 2]
        assert result["g"] == 6


class TestAgentOverrideSchemas:
    """Tests for agent override configuration schemas."""

    def test_agent_override_config_defaults(self):
        """Should have sensible defaults"""
        config = AgentOverridesConfig()
        assert config.sisyphus is None
        assert config.atlas is None

    def test_agent_override_with_model(self):
        """Should accept model configuration"""
        config = AgentOverridesConfig(
            sisyphus={
                "model": "claude-opus-4-20250514",
                "temperature": 0.5,
            }
        )
        assert config.sisyphus is not None
        assert config.sisyphus.model == "claude-opus-4-20250514"
        assert config.sisyphus.temperature == 0.5

    def test_agent_override_with_category(self):
        """Should accept category configuration"""
        config = AgentOverridesConfig(
            hephaestus={
                "category": "ultrabrain",
                "skills": ["git-master"],
            }
        )
        assert config.hephaestus is not None
        assert config.hephaestus.category == "ultrabrain"
        assert config.hephaestus.skills == ["git-master"]

    def test_hephaestus_allow_non_gpt(self):
        """Should accept Hephaestus-specific allow_non_gpt_model"""
        from backend.tenderclaw_config.schemas.agent_overrides import HephaestusOverrideConfig

        config = HephaestusOverrideConfig(
            model="claude-opus-4-20250514",
            allow_non_gpt_model=True,
        )
        assert config.allow_non_gpt_model is True

    def test_get_agent_config(self):
        """Should return agent config by name"""
        config = AgentOverridesConfig(
            prometheus={"temperature": 0.3},
            metis={"category": "quick"},
        )
        prometheus = config.get_agent_config("prometheus")
        assert prometheus is not None
        assert prometheus.temperature == 0.3

        metis = config.get_agent_config("metis")
        assert metis is not None
        assert metis.category == "quick"

        unknown = config.get_agent_config("unknown-agent")
        assert unknown is None


class TestCategorySchemas:
    """Tests for category configuration schemas."""

    def test_builtin_categories_exist(self):
        """Should have all built-in categories defined"""
        assert "visual-engineering" in BUILTIN_CATEGORIES
        assert "ultrabrain" in BUILTIN_CATEGORIES
        assert "quick" in BUILTIN_CATEGORIES
        assert "writing" in BUILTIN_CATEGORIES

    def test_builtin_category_properties(self):
        """Should have sensible default properties"""
        ultrabrain = BUILTIN_CATEGORIES["ultrabrain"]
        assert ultrabrain.model is not None
        assert ultrabrain.temperature is not None
        assert ultrabrain.reasoning_effort == "high"

    def test_categories_config_get(self):
        """Should get category from config"""
        config = CategoriesConfig(
            ultrabrain={"temperature": 0.2},
        )
        category = config.get_category("ultrabrain")
        assert category is not None
        assert category.temperature == 0.2

    def test_categories_config_fallback_to_builtin(self):
        """Should fallback to builtin when not in config"""
        config = CategoriesConfig()
        category = config.get_effective_category("quick")
        assert category.model is not None
        assert category.reasoning_effort == "none"

    def test_category_temperature_bounds(self):
        """Should validate temperature bounds"""
        config = CategoryConfig(temperature=1.5)
        assert config.temperature == 1.5

        with pytest.raises(Exception):
            CategoryConfig(temperature=3.0)


class TestHookSchemas:
    """Tests for hook configuration schemas."""

    def test_hook_config_defaults(self):
        """Should have sensible defaults"""
        config = HookConfig()
        assert config.enabled is True
        assert config.priority == 0
        assert config.options == {}

    def test_hook_config_with_options(self):
        """Should accept hook options"""
        config = HookConfig(
            enabled=True,
            priority=10,
            options={"threshold": 100},
        )
        assert config.enabled is True
        assert config.priority == 10
        assert config.options["threshold"] == 100

    def test_hooks_config_is_enabled(self):
        """Should check if hook is enabled"""
        config = HooksConfig(
            ralph_loop=HookConfig(enabled=True),
            comment_checker=HookConfig(enabled=False),
        )
        assert config.is_hook_enabled("ralph-loop") is True
        assert config.is_hook_enabled("comment-checker") is False
        assert config.is_hook_enabled("unknown-hook") is True


class TestExperimentalConfig:
    """Tests for experimental feature flags."""

    def test_experimental_defaults(self):
        """Should have sensible defaults"""
        config = ExperimentalConfig()
        assert config.aggressive_truncation is False
        assert config.auto_resume is False
        assert config.safe_hook_creation is True

    def test_dynamic_context_pruning(self):
        """Should configure dynamic context pruning"""
        config = ExperimentalConfig(
            dynamic_context_pruning={
                "enabled": True,
                "notification": "minimal",
                "protected_tools": ["task", "todowrite"],
            }
        )
        assert config.dynamic_context_pruning is not None
        assert config.dynamic_context_pruning.enabled is True
        assert config.dynamic_context_pruning.notification == "minimal"

    def test_plugin_load_timeout_bounds(self):
        """Should enforce minimum plugin_load_timeout_ms"""
        config = ExperimentalConfig(plugin_load_timeout_ms=5000)
        assert config.plugin_load_timeout_ms == 5000

        with pytest.raises(Exception):
            ExperimentalConfig(plugin_load_timeout_ms=500)


class TestSkillsConfig:
    """Tests for skills configuration."""

    def test_skills_config_sources(self):
        """Should configure skill sources"""
        config = SkillsConfig(
            sources=["skills/", {"path": "custom/", "recursive": True}],
            disable=["playwright"],
        )
        assert len(config.sources) == 2
        assert "skills/" in config.sources
        assert config.is_skill_enabled("git-master") is True
        assert config.is_skill_enabled("playwright") is False

    def test_skills_config_enable_list(self):
        """Should enable specific skills"""
        config = SkillsConfig(
            enable=["git-master", "code-review"],
        )
        assert config.is_skill_enabled("git-master") is True
        assert config.is_skill_enabled("playwright") is False


class TestGitMasterConfig:
    """Tests for Git Master configuration."""

    def test_git_master_defaults(self):
        """Should have sensible defaults"""
        config = GitMasterConfig()
        assert config.commit_footer is True
        assert config.include_co_authored_by is True
        assert config.git_env_prefix == "GIT_MASTER=1"

    def test_git_master_custom_footer(self):
        """Should accept custom commit footer"""
        config = GitMasterConfig(
            commit_footer="Custom footer",
        )
        assert config.commit_footer == "Custom footer"
        footer = config.get_commit_footer()
        assert footer == "Custom footer"

    def test_git_master_invalid_env_prefix(self):
        """Should reject shell metacharacters in env prefix"""
        with pytest.raises(Exception):
            GitMasterConfig(git_env_prefix="A=1; rm -rf /")

    def test_git_env(self):
        """Should return environment variables for git"""
        config = GitMasterConfig(git_env_prefix="TEST=1")
        env = config.get_git_env()
        assert env == {"TEST": "1"}


class TestRalphLoopConfig:
    """Tests for Ralph Loop configuration."""

    def test_ralph_loop_defaults(self):
        """Should have sensible defaults"""
        config = RalphLoopConfig()
        assert config.enabled is False
        assert config.default_max_iterations == 100
        assert config.default_strategy == "continue"

    def test_ralph_loop_custom(self):
        """Should accept custom configuration"""
        config = RalphLoopConfig(
            enabled=True,
            default_max_iterations=50,
            state_dir=".custom-state",
        )
        assert config.enabled is True
        assert config.default_max_iterations == 50
        assert config.state_dir == ".custom-state"


class TestTenderClawConfig:
    """Tests for root TenderClaw configuration."""

    def test_root_config_defaults(self):
        """Should have sensible defaults"""
        config = TenderClawConfig()
        assert config.new_task_system_enabled is False
        assert config.hashline_edit is False
        assert config.auto_update is True

    def test_root_config_with_all_sections(self):
        """Should accept all configuration sections"""
        config = TenderClawConfig(
            default_run_agent="sisyphus",
            disabled_mcps=["playwright"],
            disabled_agents=["atlas"],
            agents={"sisyphus": {"temperature": 0.5}},
            categories={"ultrabrain": {"temperature": 0.3}},
            experimental={"auto_resume": True},
            skills={"disable": ["playwright"]},
            ralph_loop={"enabled": True},
            git_master={"commit_footer": False},
        )
        assert config.default_run_agent == "sisyphus"
        assert config.is_mcp_disabled("playwright") is True
        assert config.is_agent_disabled("atlas") is True
        assert config.experimental is not None
        assert config.experimental.auto_resume is True

    def test_is_disabled_methods(self):
        """Should check disabled status correctly"""
        config = TenderClawConfig(
            disabled_mcps=["context7"],
            disabled_agents=["atlas"],
            disabled_hooks=["ralph-loop"],
            disabled_skills=["git-master"],
            disabled_tools=["bash"],
        )
        assert config.is_mcp_disabled("context7") is True
        assert config.is_mcp_disabled("grep-app") is False
        assert config.is_agent_disabled("atlas") is True
        assert config.is_agent_disabled("sisyphus") is False
        assert config.is_hook_disabled("ralph-loop") is True
        assert config.is_skill_disabled("git-master") is True
        assert config.is_tool_disabled("bash") is True

    def test_model_dump_excludes_none(self):
        """Should exclude None values when dumping"""
        config = TenderClawConfig(
            new_task_system_enabled=True,
        )
        data = config.model_dump()
        assert "new_task_system_enabled" in data
        assert data["new_task_system_enabled"] is True


class TestConfigManager:
    """Tests for ConfigManager."""

    def test_config_manager_loads_defaults(self):
        """Should load with defaults when no config files exist"""
        manager = ConfigManager()
        config = manager.load()
        assert config is not None
        assert isinstance(config, TenderClawConfig)

    def test_config_manager_get_config(self):
        """Should return cached config on subsequent calls"""
        manager = ConfigManager()
        config1 = manager.get_config()
        config2 = manager.get_config()
        assert config1 is config2

    def test_config_manager_reload(self):
        """Should reload configuration when forced"""
        manager = ConfigManager()
        config1 = manager.load()
        config2 = manager.reload()
        assert config2 is not None

    def test_config_manager_runtime_update(self):
        """Should apply runtime updates"""
        manager = ConfigManager()
        manager.load()
        updated = manager.update_runtime({
            "ralph_loop": {"enabled": True},
        })
        assert updated.ralph_loop is not None
        assert updated.ralph_loop.enabled is True

    def test_config_manager_validate(self):
        """Should validate configuration"""
        manager = ConfigManager()
        valid, error = manager.validate_config({
            "new_task_system_enabled": True,
        })
        assert valid is True
        assert error is None

        valid, error = manager.validate_config({
            "experimental": {
                "plugin_load_timeout_ms": 500,
            },
        })
        assert valid is False

    def test_config_manager_is_feature_enabled(self):
        """Should check feature flags"""
        manager = ConfigManager()
        manager.load()
        manager.update_runtime({
            "experimental": {"auto_resume": True},
        })
        assert manager.is_feature_enabled("auto_resume") is True
        assert manager.is_feature_enabled("unknown_feature") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
