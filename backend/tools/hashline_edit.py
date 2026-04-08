"""Hashline edit tool - hash-anchored safe editing."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HashlineLine:
    """A line with hash anchor."""
    number: int
    content: str
    hash: str


@dataclass
class HashlineEdit:
    """A hash-anchored edit operation."""
    line_start: int
    line_end: int
    content_hash: str
    new_content: str
    file_path: str


@dataclass
class HashlineResult:
    """Result of a hashline operation."""
    success: bool
    content: str | None = None
    error: str | None = None
    hashlines: list[HashlineLine] | None = None
    metadata: dict[str, Any] | None = None


class HashlineEditor:
    """
    Hash-anchored edit tool.
    
    Each line gets a content hash for safe, precise edits.
    Prevents stale-line errors by validating content before modification.
    
    Inspired by oh-my-openagent's hashline implementation.
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.HashlineEditor")

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute a short hash for content."""
        return hashlib.md5(content.encode()).hexdigest()[:4].upper()

    def enhance_content(self, content: str) -> list[HashlineLine]:
        """
        Enhance content with hash anchors.
        
        Each line becomes: "LINE#HASH| content"
        Example:
        ```
        11#VK| function hello() {
        22#XJ|   return "world";
        33#MB| }
        ```
        """
        lines = content.split("\n")
        hashlines = []
        
        for i, line in enumerate(lines, 1):
            hash_val = self.compute_hash(line)
            hashlines.append(HashlineLine(
                number=i,
                content=line,
                hash=hash_val
            ))
            
        return hashlines

    def format_hashlines(self, hashlines: list[HashlineLine]) -> str:
        """Format hashlines as enhanced content."""
        formatted = []
        for hl in hashlines:
            formatted.append(f"{hl.number:4d}#{hl.hash}| {hl.content}")
        return "\n".join(formatted)

    def parse_hashline_ref(self, reference: str) -> tuple[int, str] | None:
        """
        Parse a hashline reference like "LINE#HASH" or "LINE#HASH-CONTENT".
        
        Returns (line_number, hash) tuple or None if invalid.
        """
        import re
        
        pattern = r"(\d+)#([A-Z0-9]{2,4})(?:-.+)?"
        match = re.match(pattern, reference.strip())
        
        if match:
            return int(match.group(1)), match.group(2)
        return None

    def validate_hash(self, line_number: int, content: str, expected_hash: str) -> bool:
        """Validate that content matches expected hash."""
        actual_hash = self.compute_hash(content)
        return actual_hash == expected_hash

    def create_edit(self, reference: str, new_content: str, file_path: str) -> HashlineEdit | None:
        """
        Create an edit from a hashline reference.
        
        Format: "LINE#HASH" or "LINE#HASH-new_content"
        """
        parsed = self.parse_hashline_ref(reference)
        if not parsed:
            return None
            
        line_number, content_hash = parsed
        
        return HashlineEdit(
            line_start=line_number,
            line_end=line_number,
            content_hash=content_hash,
            new_content=new_content,
            file_path=file_path
        )

    def apply_edit(
        self,
        content: str,
        edit: HashlineEdit,
        validate: bool = True
    ) -> HashlineResult:
        """
        Apply a hashline edit to content.
        
        Args:
            content: Original file content
            edit: HashlineEdit to apply
            validate: Whether to validate hashes before edit
            
        Returns:
            HashlineResult with new content or error
        """
        lines = content.split("\n")
        
        if edit.line_start < 1 or edit.line_start > len(lines):
            return HashlineResult(
                success=False,
                error=f"Line {edit.line_start} out of range (1-{len(lines)})"
            )

        if validate:
            target_line = lines[edit.line_start - 1]
            if not self.validate_hash(edit.line_start, target_line, edit.content_hash):
                return HashlineResult(
                    success=False,
                    error=f"Hash mismatch at line {edit.line_start}. Content may have changed."
                )

        new_lines = lines[:edit.line_start - 1]
        new_lines.extend(edit.new_content.split("\n"))
        new_lines.extend(lines[edit.line_end:])
        
        new_content = "\n".join(new_lines)
        
        return HashlineResult(
            success=True,
            content=new_content,
            metadata={
                "line_edited": edit.line_start,
                "original_hash": edit.content_hash
            }
        )

    def apply_replace(
        self,
        content: str,
        old_content: str,
        new_content: str,
        validate: bool = True
    ) -> HashlineResult:
        """
        Apply a simple replace operation with optional hash validation.
        
        For simple replacements without hash anchors.
        """
        if old_content not in content:
            return HashlineResult(
                success=False,
                error="Old content not found in file"
            )

        new_file_content = content.replace(old_content, new_content, 1)
        
        return HashlineResult(
            success=True,
            content=new_file_content,
            metadata={"replacements": 1}
        )


class HashlineManager:
    """Manager for hashline operations."""

    def __init__(self):
        self.editor = HashlineEditor()
        self._file_hashes: dict[str, list[HashlineLine]] = {}

    def read_with_hashes(self, file_path: str, content: str) -> str:
        """
        Read a file and enhance with hash anchors.
        
        Stores hashes for later validation.
        """
        hashlines = self.editor.enhance_content(content)
        self._file_hashes[file_path] = hashlines
        return self.editor.format_hashlines(hashlines)

    def edit_with_hash(
        self,
        file_path: str,
        content: str,
        reference: str,
        new_content: str
    ) -> HashlineResult:
        """Edit a file using a hashline reference."""
        edit = self.editor.create_edit(reference, new_content, file_path)
        if not edit:
            return HashlineResult(
                success=False,
                error=f"Invalid hashline reference: {reference}"
            )
            
        return self.editor.apply_edit(content, edit)

    def validate_line(self, file_path: str, line_number: int, content: str) -> bool:
        """Validate that a line hasn't changed since last read."""
        if file_path not in self._file_hashes:
            return True
            
        hashlines = self._file_hashes[file_path]
        for hl in hashlines:
            if hl.number == line_number:
                return self.editor.validate_hash(line_number, content, hl.hash)
                
        return True

    def clear_hashes(self, file_path: str | None = None) -> None:
        """Clear stored hashes."""
        if file_path:
            self._file_hashes.pop(file_path, None)
        else:
            self._file_hashes.clear()
