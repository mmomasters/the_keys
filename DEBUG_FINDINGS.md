# Debug Findings - The Keys Integration

## Test Date: 2026-01-30 11:31

## Summary
Successfully connected to The Keys API and gateway. The original error "No gateway accessory found for this lock" was **NOT reproduced**. All locks properly have gateway accessories. However, discovered a different issue with gateway HTTP communication.

## Test Configuration
- **Username**: +33650868488
- **Gateway**: tkgateway.mooo.com:59856
- **Gateway Version**: 65
- **Rate Limiting**: 
  - Heavy operations: 5.0s
  - Light operations: 1.0s

## ✅ Successful Components

### 1. Authentication
- API authentication successful
- Access token retrieved properly

### 2. User Data Retrieval
- Found 6 locks for user
- All locks have gateway accessories properly configured:
  - Lock "1A" (ID: 3723) - Gateway ID: 12087 ✅
  - Lock "broken charge" (ID: 3726) - Gateway ID: 12087 ✅
  - Lock "1B" (ID: 3733) - Gateway ID: 12087 ✅
  - Lock "1D" (ID: 3735) - Gateway ID: 12087 ✅
  - Lock "fixed" (ID: 11503) - Gateway ID: 12087 ✅
  - Lock "1C" (ID: 19649) - Gateway ID: 12087 ✅

### 3. Gateway Detection
- Gateway properly detected with manual IP
- 12 devices total (1 gateway + 6 locks, each lock paired with gateway)
- Gateway host correctly set: `tkgateway.mooo.com:59856`

### 4. Gateway Status Queries
- Initial gateway status: "Synchronizing gw"
- After 15 seconds: Gateway transitioned to "Scanning"
- Status endpoint (`/status`) working correctly

### 5. Rate Limiting
- Successfully implemented with configurable delays
- Light operations (1.0s delay) working for gateway status checks
- Heavy operations (5.0s delay) prepared for lock operations
- Rate limit logging visible in debug output

## ❌ Issue Discovered

### Gateway Lock Status Query Failure

**Error**: `ConnectionResetError: [Errno 104] Connection reset by peer`

**Details**:
- Occurs when POSTing to `/locker_status` endpoint
- Connection is reset by the gateway itself
- Happens after gateway finishes synchronizing and enters "Scanning" state

**Possible Causes**:
1. Gateway may still be initializing locks during "Scanning" phase
2. Gateway might require additional delay after status change
3. Request format or parameters might need adjustment
4. Gateway may have additional rate limiting at hardware level

**Stack Trace Location**:
```
File "custom_components/the_keys/the_keyspy/devices/gateway.py", line 166, in __http_request
    response = session.post(full_url, data=data)
requests.exceptions.ConnectionError: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))
```

## Recommendations

### 1. **Add Delay After Gateway Scanning Status**
Wait an additional 5-10 seconds after gateway reports "Scanning" before attempting lock queries.

### 2. **Implement Retry Logic with Exponential Backoff**
When gateway resets connection, retry with increasing delays (1s, 2s, 5s, 10s).

### 3. **Enhanced Error Handling**
Catch `ConnectionResetError` specifically and provide helpful error messages to users.

### 4. **Gateway Ready Detection**
Instead of just checking for "Synchronizing gw", also wait for stable "Idle" or similar state.

### 5. **Rate Limit Tuning**
Consider increasing heavy operation delay to 10s for initial testing to avoid overwhelming gateway.

## Rate Limiting Implementation ✅

Successfully added rate limiting to all gateway operations:

### Configuration Constants (const.py)
```python
# Rate limiting for gateway communication 
CONF_RATE_LIMIT_DELAY = "rate_limit_delay"  # Heavy operations
CONF_RATE_LIMIT_DELAY_LIGHT = "rate_limit_delay_light"  # Light operations

DEFAULT_RATE_LIMIT_DELAY = 5.0  # Heavy: open/close/calibrate/locker_status
DEFAULT_RATE_LIMIT_DELAY_LIGHT = 1.0  # Light: gateway status/list/sync
```

### Implementation Details
- Heavy operations (5.0s): `locker_open`, `locker_close`, `locker_calibrate`, `locker_status`
- Light operations (1.0s): `status`, `update`, `synchronize`, `locker_synchronize`, `locker_update`
- Rate limiting enforced at instance level (per gateway)
- Debug logging shows rate limit waits

### Testing Evidence
Log excerpt showing rate limiting in action:
```
2026-01-30 11:31:22,674 - the_keyspy.devices.gateway - DEBUG - [Rate Limit] light operation - waiting 0.86s before next request...
```

## Original Error Status

The original error **"No gateway accessory found for this lock"** appears to be:
- **Not related to missing gateway accessories** (all locks have them)
- **Possibly a transient condition** during gateway initialization
- **May occur** when config flow runs before gateway completes synchronization

## Next Steps for Production

1. ✅ Rate limiting implemented
2. ⚠️ Add gateway readiness checks before lock operations  
3. ⚠️ Implement connection reset retry logic
4. ⚠️ Add user-friendly error messages for gateway synchronization states
5. ⚠️ Consider adding config option to wait for gateway ready during setup

## Files Modified

1. `custom_components/the_keys/const.py` - Added rate limit constants
2. `custom_components/the_keys/the_keyspy/devices/gateway.py` - Implemented rate limiting
3. `debug_test.py` - Created comprehensive debug script (can be removed before deployment)
