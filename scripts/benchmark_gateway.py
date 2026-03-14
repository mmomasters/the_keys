#!/usr/bin/env python3
"""
Benchmark script for The Keys Gateway
Tests response times and optimal rate limit delays.
"""
import sys
import time
import statistics
import json

sys.path.insert(0, '/home/debian/the_keys/custom_components/the_keys')

from the_keyspy.api import TheKeysApi
from the_keyspy.devices.gateway import TheKeysGateway

USERNAME = '+33650868488'
PASSWORD = 'aprilia131'
GATEWAY_HOST = 'tkgateway.mooo.com:59856'

print("=" * 60)
print("The Keys Gateway Benchmark")
print("=" * 60)

# ─── Step 1: Login and get lock ───────────────────────────────
print("\n[1] Authenticating and discovering devices...")
api = TheKeysApi(USERNAME, PASSWORD, GATEWAY_HOST, rate_limit_delay=0, rate_limit_delay_light=0)
devices = api.get_devices()

locks = [d for d in devices if hasattr(d, '_identifier')]
gateways = [d for d in devices if hasattr(d, '_host') and not hasattr(d, '_identifier')]

print(f"    Found {len(locks)} lock(s), {len(gateways)} gateway(s)")

if not gateways:
    print("ERROR: No gateway found!")
    sys.exit(1)

gateway = gateways[0]
gateway._rate_limit_delay = 0        # zero for benchmark sections 2–4
gateway._rate_limit_delay_light = 0  # zero for benchmark sections 2–4

# ─── Step 2: Benchmark gateway /status ───────────────────────
print("\n[2] Benchmarking gateway /status (10 sequential calls, no delay)...")
times = []
errors = 0
for i in range(10):
    start = time.time()
    try:
        result = gateway.status()
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"    Call {i+1:2d}: {elapsed*1000:.0f}ms  → {result.get('current_status','?')}")
    except Exception as e:
        errors += 1
        elapsed = time.time() - start
        print(f"    Call {i+1:2d}: ERROR after {elapsed*1000:.0f}ms — {type(e).__name__}: {str(e)[:60]}")

if times:
    print(f"\n    Results: min={min(times)*1000:.0f}ms  avg={statistics.mean(times)*1000:.0f}ms  max={max(times)*1000:.0f}ms  errors={errors}")

# ─── Step 3: Benchmark locker_status ─────────────────────────
if locks:
    lock = locks[0]
    lock._gateway._rate_limit_delay = 0
    lock._gateway._rate_limit_delay_light = 0

    print(f"\n[3] Benchmarking locker_status for '{lock.name}' (5 sequential calls, no delay)...")
    times2 = []
    errors2 = 0
    for i in range(5):
        start = time.time()
        try:
            result = lock.status()
            elapsed = time.time() - start
            times2.append(elapsed)
            print(f"    Call {i+1}: {elapsed*1000:.0f}ms  → status={result.get('status','?')}  pos={result.get('position','?')}  code={result.get('code','?')}")
        except Exception as e:
            errors2 += 1
            elapsed = time.time() - start
            print(f"    Call {i+1}: ERROR after {elapsed*1000:.0f}ms — {str(e)[:80]}")
        time.sleep(0.2)  # tiny gap to not overwhelm

    if times2:
        print(f"\n    Results: min={min(times2)*1000:.0f}ms  avg={statistics.mean(times2)*1000:.0f}ms  max={max(times2)*1000:.0f}ms  errors={errors2}")

    # ─── Step 4: Find minimum safe delay ──────────────────────
    print(f"\n[4] Finding minimum safe inter-request delay for locker_status...")
    for delay in [0.0, 0.5, 1.0, 2.0, 3.0]:
        print(f"\n    Testing delay={delay:.1f}s between requests (3 calls)...")
        success_count = 0
        call_times = []
        for i in range(3):
            if i > 0:
                time.sleep(delay)
            start = time.time()
            try:
                result = lock.status()
                elapsed = time.time() - start
                call_times.append(elapsed)
                success_count += 1
                status = result.get('status', '?')
                code = result.get('code', '?')
                print(f"      Call {i+1}: {elapsed*1000:.0f}ms  OK  status={status}  code={code}")
            except Exception as e:
                elapsed = time.time() - start
                err_str = str(e)[:100]
                print(f"      Call {i+1}: {elapsed*1000:.0f}ms  FAIL  {err_str}")
        
        success_rate = success_count / 3 * 100
        avg = statistics.mean(call_times) * 1000 if call_times else 0
        print(f"      → Success rate: {success_rate:.0f}%  avg response: {avg:.0f}ms")
        
        if success_rate == 100:
            print(f"      ✓ delay={delay:.1f}s is sufficient!")
            break
        else:
            print(f"      ✗ delay={delay:.1f}s has failures, trying longer delay...")

    # ─── Step 5: Simulate HA coordinator cycle ────────────────
    print(f"\n[5] Simulating HA coordinator poll cycle (gateway.status then 3 locks, with real delays)...")
    print(f"    Rate limits: heavy={1.0}s, light={0.5}s (reset AFTER response)")

    # Fresh gateway with real delays
    sim_gateway = TheKeysGateway(
        gateway.id, gateway._host,
        rate_limit_delay=1.0,
        rate_limit_delay_light=0.5
    )
    # Point the lock to the sim gateway temporarily
    original_gateway = lock._gateway
    lock._gateway = sim_gateway

    cycle_start = time.time()

    # Step 1: Gateway status (like coordinator pre-check)
    t = time.time()
    try:
        gw_status = sim_gateway.status()
        print(f"    gateway.status():          {(time.time()-t)*1000:.0f}ms → {gw_status.get('current_status','?')}")
    except Exception as e:
        print(f"    gateway.status():          FAIL — {str(e)[:80]}")

    # Steps 2-4: 3 lock status calls (simulating 3 locks on same gateway)
    for i in range(3):
        t = time.time()
        try:
            result = lock._gateway.locker_status(lock._identifier, lock._share_code)
            print(f"    lock{i+1}.locker_status():   {(time.time()-t)*1000:.0f}ms → status={result.get('status','?')}  code={result.get('code','?')}")
        except Exception as e:
            print(f"    lock{i+1}.locker_status():   FAIL — {str(e)[:80]}")

    total = time.time() - cycle_start
    print(f"\n    Total cycle time: {total:.1f}s  (scan interval = 60s)")

    # Restore original gateway
    lock._gateway = original_gateway

print("\n" + "=" * 60)
print("Benchmark complete!")
print("=" * 60)
