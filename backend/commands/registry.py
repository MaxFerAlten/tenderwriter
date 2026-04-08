"""Commands registry and base command class."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CommandConfig:
    """Configuration for a command."""
    name: str
    description: str
    usage: str | None = None
    aliases: list[str] | None = None


@dataclass
class CommandResult:
    """Result from command execution."""
    success: bool
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class BaseCommand(ABC):
    """Base class for all commands."""

    def __init__(self, config: CommandConfig | None = None):
        self.config = config or CommandConfig(
            name=self.__class__.__name__,
            description="No description"
        )
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def description(self) -> str:
        return self.config.description

    @abstractmethod
    async def execute(self, args: str, context: dict[str, Any] | None = None) -> CommandResult:
        """Execute the command with arguments."""
        pass

    def parse_args(self, args: str) -> dict[str, Any]:
        """Parse command arguments into a dictionary."""
        parts = args.split()
        parsed = {"_": []}
        current_key = None
        
        for part in parts:
            if part.startswith("--"):
                current_key = part[2:]
                parsed[current_key] = True
            elif part.startswith("-"):
                current_key = part[1:]
                parsed[current_key] = True
            elif current_key:
                if isinstance(parsed[current_key], bool):
                    parsed[current_key] = part
                else:
                    parsed[current_key] = part
                current_key = None
            else:
                parsed["_"].append(part)
                
        return parsed


class CommandRegistry:
    """Registry for all available commands."""

    _commands: dict[str, type[BaseCommand]] = {}
    _instances: dict[str, BaseCommand] = {}

    @classmethod
    def register(cls, name: str | None = None):
        """Decorator to register a command class."""
        def decorator(command_class: type[BaseCommand]):
            cmd_name = name or command_class.__name__.lower().replace("command", "")
            cls._commands[cmd_name] = command_class
            return command_class
        return decorator

    @classmethod
    def get(cls, name: str) -> BaseCommand:
        """Get or create a command instance by name."""
        if name not in cls._instances:
            if name not in cls._commands:
                raise ValueError(f"Unknown command: {name}")
            cls._instances[name] = cls._commands[name]()
        return cls._instances[name]

    @classmethod
    def list_commands(cls) -> list[str]:
        """List all registered command names."""
        return list(cls._commands.keys())

    @classmethod
    async def execute(cls, name: str, args: str, context: dict[str, Any] | None = None) -> CommandResult:
        """Execute a command by name."""
        try:
            command = cls.get(name)
            return await command.execute(args, context)
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    @classmethod
    def get_help(cls, name: str) -> str | None:
        """Get help text for a command."""
        try:
            command = cls.get(name)
            help_text = f"# /{command.name}\n\n{command.description}"
            
            if command.config.usage:
                help_text += f"\n\n## Usage\n```\n{command.config.usage}\n```"
                
            return help_text
        except ValueError:
            return None


def command(name: str | None = None):
    """Shorthand decorator for command registration."""
    return CommandRegistry.register(name)
