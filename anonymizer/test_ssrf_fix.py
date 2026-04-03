from unittest.mock import patch

from anonymizer._test_support import load_anonymizer_app_module


_is_allowed_target_url = load_anonymizer_app_module()._is_allowed_target_url

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


def test_anonymizer_blocks_explicit_private_ip_targets():
    """Direct private IPs should never be accepted as relay destinations."""

    assert _is_allowed_target_url("http://10.0.0.5") is False
    assert _is_allowed_target_url("http://172.16.0.10") is False
    assert _is_allowed_target_url("http://192.168.1.7") is False
