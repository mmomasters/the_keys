#!/usr/bin/env python3
"""Test script for gateway address validation."""

import re
import ipaddress


def _validate_gateway_address(gateway: str) -> bool:
    """Validate gateway address (IP, hostname, or hostname:port format).
    
    Accepts:
    - IPv4 addresses (e.g., 192.168.1.1)
    - IPv6 addresses (e.g., ::1, 2001:db8::1)
    - Hostnames (e.g., gateway.local, example.com)
    - Hostname with port (e.g., gateway.local:8080, example.com:443)
    - IP addresses with port (e.g., 192.168.1.1:8080, [::1]:8080)
    """
    if not gateway:
        return False
    
    # Check if there's a port specified
    port = None
    host = gateway
    
    # Handle IPv6 with port: [::1]:8080
    if gateway.startswith('['):
        match = re.match(r'^\[([^\]]+)\]:(\d+)$', gateway)
        if match:
            host = match.group(1)
            port = match.group(2)
        else:
            # Just IPv6 without port: [::1]
            match = re.match(r'^\[([^\]]+)\]$', gateway)
            if match:
                host = match.group(1)
            else:
                return False
    # Handle IPv4/hostname with port: example.com:8080
    elif ':' in gateway:
        # Could be IPv6 without brackets or hostname:port or IPv4:port
        # Try to parse as IPv6 first
        try:
            ipaddress.IPv6Address(gateway)
            host = gateway
            port = None
        except ValueError:
            # Not IPv6, try hostname:port or IPv4:port
            parts = gateway.rsplit(':', 1)
            if len(parts) == 2:
                host = parts[0]
                port = parts[1]
    
    # Validate port if present
    if port is not None:
        try:
            port_num = int(port)
            if port_num < 1 or port_num > 65535:
                return False
        except ValueError:
            return False
    
    # Validate host part
    # Try IP address first
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    
    # Validate as hostname (RFC 1123)
    # Hostname can contain letters, digits, hyphens, and dots
    # Each label must start and end with alphanumeric
    # Total length must be 1-253 characters
    if len(host) > 253 or len(host) == 0:
        return False
    
    # Hostname regex pattern
    hostname_pattern = re.compile(
        r'^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(\.[a-zA-Z0-9-]{1,63})*$'
    )
    
    return bool(hostname_pattern.match(host))


def test_validation():
    """Test various gateway address formats."""
    
    test_cases = [
        # Valid IPv4 addresses
        ("192.168.1.1", True, "IPv4 address"),
        ("10.0.0.1", True, "IPv4 address"),
        ("192.168.1.1:8080", True, "IPv4 address with port"),
        ("192.168.1.1:443", True, "IPv4 address with port 443"),
        
        # Valid IPv6 addresses
        ("::1", True, "IPv6 loopback"),
        ("2001:db8::1", True, "IPv6 address"),
        ("[::1]:8080", True, "IPv6 with port"),
        ("[2001:db8::1]:443", True, "IPv6 with port"),
        
        # Valid hostnames
        ("gateway.local", True, "Hostname with .local"),
        ("example.com", True, "Domain name"),
        ("my-gateway", True, "Hostname with hyphen"),
        ("gateway123", True, "Hostname with numbers"),
        ("sub.domain.example.com", True, "Subdomain"),
        
        # Valid hostnames with port
        ("gateway.local:8080", True, "Hostname with port"),
        ("example.com:443", True, "Domain with HTTPS port"),
        ("my-gateway:3000", True, "Hostname with port"),
        ("sub.domain.example.com:8443", True, "Subdomain with port"),
        
        # Invalid cases
        ("", False, "Empty string"),
        ("192.168.1.1:99999", False, "Port out of range"),
        ("192.168.1.1:0", False, "Port zero"),
        ("192.168.1.1:-100", False, "Negative port"),
        ("192.168.1.1:abc", False, "Non-numeric port"),
        ("-invalid.com", False, "Hostname starting with hyphen"),
        ("invalid-.com", False, "Label ending with hyphen"),
        ("invalid..com", False, "Double dot in hostname"),
        (".invalid.com", False, "Hostname starting with dot"),
        ("invalid.com.", False, "Hostname ending with dot"),
        ("host name.com", False, "Hostname with space"),
        ("a" * 254, False, "Hostname too long"),
    ]
    
    print("Testing gateway address validation:\n")
    print(f"{'Test Case':<40} {'Expected':<10} {'Result':<10} {'Status'}")
    print("-" * 80)
    
    passed = 0
    failed = 0
    
    for gateway, expected, description in test_cases:
        result = _validate_gateway_address(gateway)
        status = "✓ PASS" if result == expected else "✗ FAIL"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        # Truncate long test inputs for display
        display_input = gateway[:35] + "..." if len(gateway) > 38 else gateway
        print(f"{display_input:<40} {str(expected):<10} {str(result):<10} {status}")
    
    print("-" * 80)
    print(f"\nTotal tests: {len(test_cases)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n✓ All tests passed!")
        return True
    else:
        print(f"\n✗ {failed} tests failed!")
        return False


if __name__ == "__main__":
    success = test_validation()
    exit(0 if success else 1)
