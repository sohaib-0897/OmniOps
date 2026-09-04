import socket
import ipaddress
from urllib.parse import urlparse
from typing import Optional, Dict, Any
import httpx
import trafilatura

# Prohibited IP ranges for SSRF defense
PROHIBITED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918 Class A
    ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918 Class B
    ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918 Class C
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local / Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("0.0.0.0/8"),        # Current network
    ipaddress.ip_network("224.0.0.0/4"),      # Multicast
    ipaddress.ip_network("240.0.0.0/4"),      # Reserved
    ipaddress.ip_network("::1/128"),          # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 Unique Local Address
    ipaddress.ip_network("fe80::/10"),        # IPv6 Link-Local
]

def is_ip_prohibited(ip_str: str) -> bool:
    """Check whether resolved IP falls into any forbidden internal / metadata ranges."""
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        for net in PROHIBITED_NETWORKS:
            if ip_obj in net:
                return True
        return False
    except ValueError:
        return True

def validate_url_security(url: str) -> str:
    """Validate URL scheme and resolve host IPs to prevent SSRF and DNS rebinding."""
    parsed = urlparse(url)
    if parsed.scheme not in ["http", "https"]:
        raise ValueError(f"Invalid URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")
        
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must include a valid hostname.")
        
    # Disallow common local keywords
    if hostname.lower() in ["localhost", "127.0.0.1", "0.0.0.0", "metadata.google.internal"]:
        raise ValueError(f"Security violation: Hostname '{hostname}' is restricted.")
        
    # Resolve all associated IP addresses
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for addr in addr_info:
            ip_str = addr[4][0]
            if is_ip_prohibited(ip_str):
                raise ValueError(f"Security violation: Resolved IP '{ip_str}' for host '{hostname}' is in a private or restricted network range.")
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for host '{hostname}': {e}")
        
    return url

async def fetch_web_page_content(url: str, max_size_bytes: int = 2 * 1024 * 1024) -> Dict[str, Any]:
    """Fetch external web page safely with SSRF protection and extract article text."""
    clean_url = validate_url_security(url)
    
    # Configure strict timeout and disable automatic redirects
    # Redirects are manually validated
    current_url = clean_url
    redirect_count = 0
    max_redirects = 3
    
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
        while redirect_count <= max_redirects:
            response = await client.get(current_url, headers={"User-Agent": "OmniOps-Security-Agent/1.0"})
            
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirect response missing 'Location' header.")
                from urllib.parse import urljoin
                resolved_location = urljoin(current_url, location)
                # Re-validate redirect target to prevent open redirect SSRF
                current_url = validate_url_security(resolved_location)
                redirect_count += 1
                continue
                
            if response.status_code != 200:
                raise ValueError(f"HTTP request returned status {response.status_code}")
                
            content_bytes = response.content
            if len(content_bytes) > max_size_bytes:
                raise ValueError(f"Downloaded content exceeds {max_size_bytes // (1024 * 1024)} MB limit.")
                
            html_text = response.text
            extracted_text = trafilatura.extract(html_text, include_tables=True, include_links=False)
            
            return {
                "url": current_url,
                "title": trafilatura.metadata.extract_metadata(html_text).title if trafilatura.metadata.extract_metadata(html_text) else "Web Page",
                "content": extracted_text or "",
                "extraction_status": "EXTRACTED" if extracted_text else "TEXT_EXTRACTION_UNAVAILABLE",
                "status_code": response.status_code
            }
            
    raise ValueError("Exceeded maximum allowed redirects.")
