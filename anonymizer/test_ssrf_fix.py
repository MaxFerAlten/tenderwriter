import pytest
from unittest.mock import patch
from app import _is_allowed_target_url

def test_bug_04_ssrf_anonymizer_blocks_internal_dns():
    """Verify that internal hostnames that resolve to private IPs are blocked."""
    
    # 1. Normal public IP should be allowed
    assert _is_allowed_target_url("http://google.com") is True
    
    # 2. explicit localhost should be blocked 
    assert _is_allowed_target_url("http://localhost:8080") is False
    
    # 3. Internal alias like "postgres" should be resolved to its IP and blocked
    with patch("socket.gethostbyname") as mock_dns:
        # Simulate returning a private Docker network IP
        mock_dns.return_value = "10.0.0.5"
        
        # Before the fix, "postgres" would raise ValueError in ipaddress.ip_address()
        # and bypass the check. Now it resolves the hostname first.
        assert _is_allowed_target_url("http://postgres:5432") is False
        mock_dns.assert_called_with("postgres") # This proves BUG-04 is fixed!
