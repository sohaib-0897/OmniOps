import pytest
from app.ingestion.web_fetcher import is_ip_prohibited, validate_url_security

def test_prohibited_ip_ranges():
    # Loopback
    assert is_ip_prohibited("127.0.0.1") is True
    assert is_ip_prohibited("127.0.0.2") is True
    assert is_ip_prohibited("::1") is True

    # RFC 1918 Private IPv4
    assert is_ip_prohibited("10.0.0.1") is True
    assert is_ip_prohibited("172.16.0.1") is True
    assert is_ip_prohibited("192.168.1.1") is True

    # Cloud Metadata Endpoint & IPv6
    assert is_ip_prohibited("169.254.169.254") is True
    assert is_ip_prohibited("fc00::1") is True
    assert is_ip_prohibited("fe80::1") is True

    # Public valid IP
    assert is_ip_prohibited("8.8.8.8") is False
    assert is_ip_prohibited("1.1.1.1") is False

def test_url_security_validation():
    # Loopback & local keywords
    with pytest.raises(ValueError, match="restricted"):
        validate_url_security("http://localhost/admin")
        
    with pytest.raises(ValueError, match="restricted"):
        validate_url_security("http://127.0.0.1:8000/api")

    with pytest.raises(ValueError, match="restricted"):
        validate_url_security("http://metadata.google.internal/computeMetadata/v1/")

    # Invalid scheme
    with pytest.raises(ValueError, match="scheme"):
        validate_url_security("file:///etc/passwd")

    with pytest.raises(ValueError, match="scheme"):
        validate_url_security("gopher://internal.service/")

def test_relative_redirect_url_resolution():
    from urllib.parse import urljoin
    base = "https://example.com/login"
    rel_loc = "/admin/dashboard"
    resolved = urljoin(base, rel_loc)
    assert resolved == "https://example.com/admin/dashboard"
    # Should validate clean URL
    assert validate_url_security(resolved) == "https://example.com/admin/dashboard"
