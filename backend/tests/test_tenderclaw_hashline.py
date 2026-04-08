"""Tests for hashline edit tool."""

import pytest

from backend.tools import HashlineEditor, HashlineManager


class TestHashlineEditor:
    """Tests for hashline editor."""

    def test_compute_hash(self):
        """Test hash computation."""
        editor = HashlineEditor()
        hash1 = editor.compute_hash("hello")
        hash2 = editor.compute_hash("hello")
        hash3 = editor.compute_hash("world")
        
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 4

    def test_enhance_content(self):
        """Test enhancing content with hashes."""
        editor = HashlineEditor()
        content = "line1\nline2\nline3"
        hashlines = editor.enhance_content(content)
        
        assert len(hashlines) == 3
        assert hashlines[0].number == 1
        assert hashlines[0].content == "line1"
        assert len(hashlines[0].hash) == 4

    def test_format_hashlines(self):
        """Test formatting hashlines."""
        editor = HashlineEditor()
        hashlines = editor.enhance_content("hello\nworld")
        formatted = editor.format_hashlines(hashlines)
        
        assert "1#" in formatted
        assert "hello" in formatted
        assert "2#" in formatted
        assert "world" in formatted

    def test_parse_hashline_ref(self):
        """Test parsing hashline reference."""
        editor = HashlineEditor()
        
        result = editor.parse_hashline_ref("42#ABCD")
        assert result == (42, "ABCD")
        
        result = editor.parse_hashline_ref("1#VK-test")
        assert result == (1, "VK")
        
        result = editor.parse_hashline_ref("invalid")
        assert result is None

    def test_validate_hash(self):
        """Test hash validation."""
        editor = HashlineEditor()
        content = "test content"
        hash_val = editor.compute_hash(content)
        
        assert editor.validate_hash(1, content, hash_val) is True
        assert editor.validate_hash(1, "different", hash_val) is False

    def test_apply_edit_success(self):
        """Test applying a valid edit."""
        editor = HashlineEditor()
        content = "line1\nline2\nline3"
        
        edit = editor.create_edit("2#XXXX", "new line 2", "test.txt")
        if edit:
            edit.content_hash = editor.compute_hash("line2")
            result = editor.apply_edit(content, edit)
            
            assert result.success is True
            assert "new line 2" in result.content

    def test_apply_edit_hash_mismatch(self):
        """Test applying edit with hash mismatch."""
        editor = HashlineEditor()
        content = "line1\nline2\nline3"
        
        edit = editor.create_edit("2#XXXX", "new line 2", "test.txt")
        if edit:
            edit.content_hash = "WRNG"
            result = editor.apply_edit(content, edit)
            
            assert result.success is False
            assert "Hash mismatch" in result.error


class TestHashlineManager:
    """Tests for hashline manager."""

    def test_read_with_hashes(self):
        """Test reading file with hashes."""
        manager = HashlineManager()
        content = "test\ncontent"
        
        enhanced = manager.read_with_hashes("test.txt", content)
        
        assert "1#" in enhanced
        assert "2#" in enhanced

    def test_edit_with_hash(self):
        """Test editing with hash reference."""
        manager = HashlineManager()
        content = "line1\nline2\nline3"
        
        hashlines = manager.editor.enhance_content(content)
        hash_val = hashlines[1].hash
        
        ref = f"2#{hash_val}"
        result = manager.edit_with_hash("test.txt", content, ref, "new line 2")
        
        assert result.success is True
        assert "new line 2" in result.content

    def test_clear_hashes(self):
        """Test clearing hashes."""
        manager = HashlineManager()
        manager.read_with_hashes("test.txt", "content")
        
        assert "test.txt" in manager._file_hashes
        
        manager.clear_hashes("test.txt")
        assert "test.txt" not in manager._file_hashes
