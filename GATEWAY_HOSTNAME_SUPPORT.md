# Gateway Hostname Support

## Summary

The Keys integration has been updated to support gateway hostnames with optional ports, in addition to IP addresses.

## Changes Made

### 1. Enhanced Validation Logic (`config_flow.py`)

**Previous behavior:**
- Only accepted IPv4 addresses (e.g., `192.168.1.1`)
- Used `ipaddress.ip_address()` for validation

**New behavior:**
- Accepts IPv4 addresses (e.g., `192.168.1.1`)
- Accepts IPv6 addresses (e.g., `::1`, `2001:db8::1`)
- Accepts hostnames (e.g., `gateway.local`, `example.com`)
- Accepts hostname with port (e.g., `gateway.local:8080`, `example.com:443`)
- Accepts IP addresses with port (e.g., `192.168.1.1:8080`, `[::1]:8080`)

### 2. New Validation Function

The `_validate_gateway_address()` function now supports:

- **IPv4 addresses:** `192.168.1.1`
- **IPv4 with port:** `192.168.1.1:8080`
- **IPv6 addresses:** `::1`, `2001:db8::1`
- **IPv6 with port:** `[::1]:8080`, `[2001:db8::1]:443`
- **Hostnames:** `gateway.local`, `example.com`, `my-gateway`
- **Hostnames with port:** `gateway.local:8080`, `sub.domain.example.com:8443`

### 3. Validation Rules

The function validates:
- Port numbers must be between 1-65535
- Hostnames follow RFC 1123 specification
- Hostname length must be 1-253 characters
- Each hostname label must be 1-63 characters
- Labels must start and end with alphanumeric characters
- Hyphens are allowed in the middle of labels

### 4. Updated Error Messages

Error messages have been updated in:
- `strings.json`: Base configuration
- `translations/en.json`: English translation
- `translations/fr.json`: French translation

Now displays helpful examples when validation fails:
> "Invalid gateway address format. Enter IP address, hostname, or hostname:port (e.g., 192.168.1.1, gateway.local, gateway.local:8080)"

## Testing

A comprehensive test suite (`test_gateway_validation.py`) validates 29 test cases covering:
- Valid IPv4 and IPv6 addresses
- Valid hostnames with various formats
- Port validation (valid and invalid ranges)
- Invalid hostname formats
- Edge cases

**Test Results:** ✓ All 29 tests passed

## Usage Examples

Users can now configure the gateway using any of these formats:

```yaml
# IP address only
gateway_ip: 192.168.1.1

# IP address with port
gateway_ip: 192.168.1.1:8080

# Hostname
gateway_ip: thekeys.local

# Hostname with port
gateway_ip: thekeys.local:8080

# Domain name with port
gateway_ip: myhome.example.com:8443

# IPv6 address
gateway_ip: ::1

# IPv6 address with port
gateway_ip: [::1]:8080
```

## Files Modified

1. `custom_components/the_keys/config_flow.py` - Enhanced validation logic
2. `custom_components/the_keys/strings.json` - Updated error messages
3. `custom_components/the_keys/translations/en.json` - English translations
4. `custom_components/the_keys/translations/fr.json` - French translations

## Files Added

1. `test_gateway_validation.py` - Comprehensive test suite for validation function
2. `GATEWAY_HOSTNAME_SUPPORT.md` - This documentation file

## Backward Compatibility

✅ **Fully backward compatible** - existing configurations using IP addresses will continue to work without any changes.
