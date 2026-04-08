"""Hook Configuration Schema.

Based on oh-my-openagent's HookNameSchema with 48+ built-in hooks.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


HookName = Literal[
    "todo-continuation-enforcer",
    "context-window-monitor",
    "session-recovery",
    "session-notification",
    "comment-checker",
    "tool-output-truncator",
    "question-label-truncator",
    "directory-agents-injector",
    "directory-readme-injector",
    "empty-task-response-detector",
    "think-mode",
    "model-fallback",
    "anthropic-context-window-limit-recovery",
    "preemptive-compaction",
    "rules-injector",
    "background-notification",
    "auto-update-checker",
    "startup-toast",
    "keyword-detector",
    "agent-usage-reminder",
    "non-interactive-env",
    "interactive-bash-session",
    "thinking-block-validator",
    "ralph-loop",
    "category-skill-reminder",
    "compaction-context-injector",
    "compaction-todo-preserver",
    "claude-code-hooks",
    "auto-slash-command",
    "edit-error-recovery",
    "json-error-recovery",
    "delegate-task-retry",
    "prometheus-md-only",
    "sisyphus-junior-notepad",
    "no-sisyphus-gpt",
    "no-hephaestus-non-gpt",
    "start-work",
    "atlas",
    "unstable-agent-babysitter",
    "task-resume-info",
    "stop-continuation-guard",
    "tasks-todowrite-disabler",
    "runtime-fallback",
    "write-existing-file-guard",
    "bash-file-read-guard",
    "anthropic-effort",
    "hashline-read-enhancer",
    "read-image-resizer",
    "todo-description-override",
    "webfetch-redirect-guard",
    "legacy-plugin-toast",
]

ALL_HOOK_NAMES: set[str] = set(__annotations__.get("HookName", HookName.__args__ if hasattr(HookName, "__args__") else []))


class HookConfig(BaseModel):
    """Configuration for a specific hook."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    priority: int = 0
    options: dict = {}


class HooksConfig(BaseModel):
    """Container for hook configurations."""

    model_config = ConfigDict(extra="allow")

    todo_continuation_enforcer: Optional[HookConfig] = None
    context_window_monitor: Optional[HookConfig] = None
    session_recovery: Optional[HookConfig] = None
    session_notification: Optional[HookConfig] = None
    comment_checker: Optional[HookConfig] = None
    tool_output_truncator: Optional[HookConfig] = None
    question_label_truncator: Optional[HookConfig] = None
    directory_agents_injector: Optional[HookConfig] = None
    directory_readme_injector: Optional[HookConfig] = None
    empty_task_response_detector: Optional[HookConfig] = None
    think_mode: Optional[HookConfig] = None
    model_fallback: Optional[HookConfig] = None
    anthropic_context_window_limit_recovery: Optional[HookConfig] = None
    preemptive_compaction: Optional[HookConfig] = None
    rules_injector: Optional[HookConfig] = None
    background_notification: Optional[HookConfig] = None
    auto_update_checker: Optional[HookConfig] = None
    startup_toast: Optional[HookConfig] = None
    keyword_detector: Optional[HookConfig] = None
    agent_usage_reminder: Optional[HookConfig] = None
    non_interactive_env: Optional[HookConfig] = None
    interactive_bash_session: Optional[HookConfig] = None
    thinking_block_validator: Optional[HookConfig] = None
    ralph_loop: Optional[HookConfig] = None
    category_skill_reminder: Optional[HookConfig] = None
    compaction_context_injector: Optional[HookConfig] = None
    compaction_todo_preserver: Optional[HookConfig] = None
    claude_code_hooks: Optional[HookConfig] = None
    auto_slash_command: Optional[HookConfig] = None
    edit_error_recovery: Optional[HookConfig] = None
    json_error_recovery: Optional[HookConfig] = None
    delegate_task_retry: Optional[HookConfig] = None
    prometheus_md_only: Optional[HookConfig] = None
    sisyphus_junior_notepad: Optional[HookConfig] = None
    no_sisyphus_gpt: Optional[HookConfig] = None
    no_hephaestus_non_gpt: Optional[HookConfig] = None
    start_work: Optional[HookConfig] = None
    atlas: Optional[HookConfig] = None
    unstable_agent_babysitter: Optional[HookConfig] = None
    task_resume_info: Optional[HookConfig] = None
    stop_continuation_guard: Optional[HookConfig] = None
    tasks_todowrite_disabler: Optional[HookConfig] = None
    runtime_fallback: Optional[HookConfig] = None
    write_existing_file_guard: Optional[HookConfig] = None
    bash_file_read_guard: Optional[HookConfig] = None
    anthropic_effort: Optional[HookConfig] = None
    hashline_read_enhancer: Optional[HookConfig] = None
    read_image_resizer: Optional[HookConfig] = None
    todo_description_override: Optional[HookConfig] = None
    webfetch_redirect_guard: Optional[HookConfig] = None
    legacy_plugin_toast: Optional[HookConfig] = None

    def is_hook_enabled(self, hook_name: str) -> bool:
        """Check if a hook is enabled."""
        attr_name = hook_name.replace("-", "_")
        hook = getattr(self, attr_name, None)
        if hook is None:
            return True
        return hook.enabled

    def get_hook_config(self, hook_name: str) -> Optional[HookConfig]:
        """Get configuration for a specific hook."""
        attr_name = hook_name.replace("-", "_")
        return getattr(self, attr_name, None)
