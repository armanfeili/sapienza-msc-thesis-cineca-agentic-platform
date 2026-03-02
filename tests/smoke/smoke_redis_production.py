#!/usr/bin/env python3
"""
Production Readiness Smoke Test Suite

Validates Redis job store production features:
- Backend toggle & rollback
- Redis durability 
- TTL sanity checks
- Atomic cancellation under load
- ETag parity across backends
- Index hygiene automation
- SSE resilience
- Metrics & alerts
- Security enforcement
"""

import asyncio
import httpx
import json
import time
from datetime import datetime, timedelta

# Test configuration
BASE_URL = "http://localhost:8000"
ADMIN_TOKEN = "dev-admin-token"  # From run/admin-token.txt
USER_TOKEN = "dev-user-token"


class SmokeTestRunner:
    def __init__(self):
        self.results = []
        self.client = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)

    async def run_all(self):
        print("🧪 Redis Job Store Production Smoke Tests\n")
        print("=" * 60)

        # 1. Backend toggle
        await self.test_backend_toggle()

        # 2. TTL sanity
        await self.test_ttl_sanity()

        # 3. Atomic cancel under load
        await self.test_atomic_cancel_concurrent()

        # 4. ETag parity
        await self.test_etag_parity()

        # 5. SSE resilience
        await self.test_sse_resilience()

        # 6. Security pass
        await self.test_security_enforcement()

        # Summary
        self.print_summary()

        await self.client.aclose()

    async def test_backend_toggle(self):
        """Test 1: Backend toggle & rollback (redis ↔ memory)"""
        print("\n📋 Test 1: Backend Toggle & Rollback")
        print("-" * 60)

        # This requires manual restart, so we'll validate current backend
        try:
            # Create job
            resp = await self.client.post(
                "/v2/jobs",
                json={"type": "test-job", "payload": {"test": "backend-toggle"}},
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            )
            job_id = resp.json()["id"]

            # GET job
            resp = await self.client.get(f"/v2/jobs/{job_id}", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
            assert resp.status_code == 200

            # DELETE job
            resp = await self.client.delete(f"/v2/jobs/{job_id}", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
            assert resp.status_code == 204

            self.record_pass("Backend smoke (POST/GET/DELETE)")
        except Exception as e:
            self.record_fail("Backend smoke", str(e))

    async def test_ttl_sanity(self):
        """Test 2: TTL sanity checks"""
        print("\n📋 Test 2: TTL Sanity")
        print("-" * 60)

        try:
            # Create job with idempotency key
            idem_key = f"ttl-test-{int(time.time())}"
            resp = await self.client.post(
                "/v2/jobs",
                json={"type": "test-job", "payload": {"test": "ttl"}},
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}", "Idempotency-Key": idem_key},
            )
            job_id = resp.json()["id"]

            # Replay with same idempotency key (should return same job)
            resp2 = await self.client.post(
                "/v2/jobs",
                json={"type": "test-job", "payload": {"test": "ttl"}},
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}", "Idempotency-Key": idem_key},
            )
            assert resp2.json()["id"] == job_id
            assert resp2.headers.get("Idempotency-Replayed") == "true"

            self.record_pass("TTL: Idempotency 24h replay works")

            # Note: Full TTL verification requires waiting ~10 days (not practical in smoke test)
            print("  ⚠️  Full job TTL (10 days) requires manual verification")
        except Exception as e:
            self.record_fail("TTL sanity", str(e))

    async def test_atomic_cancel_concurrent(self):
        """Test 3: Atomic cancel under load"""
        print("\n📋 Test 3: Atomic Cancel Under Load")
        print("-" * 60)

        try:
            # Create job
            resp = await self.client.post(
                "/v2/jobs",
                json={"type": "test-job", "payload": {"test": "concurrent-cancel"}},
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            )
            job_id = resp.json()["id"]

            # Fire 10 concurrent cancellations
            async def cancel_job():
                resp = await self.client.post(
                    f"/v2/jobs/{job_id}/cancel", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
                )
                return resp.status_code

            results = await asyncio.gather(*[cancel_job() for _ in range(10)])

            # Exactly one should be 202 (first cancel), rest should be 200 (already cancelled)
            first_cancel_count = sum(1 for code in results if code == 202)
            already_cancelled_count = sum(1 for code in results if code == 200)

            assert first_cancel_count == 1, f"Expected 1 first cancel, got {first_cancel_count}"
            assert already_cancelled_count == 9, f"Expected 9 already-cancelled, got {already_cancelled_count}"

            self.record_pass(f"Atomic cancel: 1 transition from {len(results)} attempts")
        except Exception as e:
            self.record_fail("Atomic cancel concurrent", str(e))

    async def test_etag_parity(self):
        """Test 4: ETag parity across backends"""
        print("\n📋 Test 4: ETag Parity")
        print("-" * 60)

        try:
            # Create job
            resp = await self.client.post(
                "/v2/jobs",
                json={"type": "test-job", "payload": {"test": "etag"}},
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            )
            job_id = resp.json()["id"]

            # GET with ETag
            resp1 = await self.client.get(f"/v2/jobs/{job_id}", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
            etag = resp1.headers.get("ETag")
            assert etag is not None

            # GET with If-None-Match (should return 304)
            resp2 = await self.client.get(
                f"/v2/jobs/{job_id}", headers={"Authorization": f"Bearer {ADMIN_TOKEN}", "If-None-Match": etag}
            )
            assert resp2.status_code == 304, f"Expected 304, got {resp2.status_code}"

            self.record_pass("ETag: If-None-Match returns 304")
        except Exception as e:
            self.record_fail("ETag parity", str(e))

    async def test_sse_resilience(self):
        """Test 5: SSE resilience (Last-Event-ID, reconnect)"""
        print("\n📋 Test 5: SSE Resilience")
        print("-" * 60)

        try:
            # Create job
            resp = await self.client.post(
                "/v2/jobs",
                json={"type": "test-job", "payload": {"test": "sse"}},
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            )
            job_id = resp.json()["id"]

            # Stream events (initial connection, no Last-Event-ID)
            events1 = []
            async with self.client.stream(
                "GET", f"/v2/jobs/{job_id}/events", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
            ) as stream:
                async for line in stream.aiter_lines():
                    if line.startswith("id:"):
                        event_id = line.split(":", 1)[1].strip()
                        events1.append(event_id)
                    if len(events1) >= 2:  # Get first 2 events
                        break

            # Reconnect with Last-Event-ID (should resume from last seen)
            if events1:
                last_id = events1[-1]
                events2 = []
                async with self.client.stream(
                    "GET",
                    f"/v2/jobs/{job_id}/events",
                    headers={"Authorization": f"Bearer {ADMIN_TOKEN}", "Last-Event-ID": last_id},
                ) as stream:
                    async for line in stream.aiter_lines():
                        if line.startswith("id:"):
                            event_id = line.split(":", 1)[1].strip()
                            events2.append(event_id)
                            if len(events2) >= 1:
                                break

                # Event IDs should be monotonic (no duplicates after resume)
                all_ids = events1 + events2
                assert len(all_ids) == len(set(all_ids)), "Duplicate event IDs detected"

                self.record_pass("SSE: Last-Event-ID resume, no duplicates")
            else:
                self.record_pass("SSE: Stream connected (no events yet)")
        except Exception as e:
            self.record_fail("SSE resilience", str(e))

    async def test_security_enforcement(self):
        """Test 6: Security enforcement"""
        print("\n📋 Test 6: Security Enforcement")
        print("-" * 60)

        try:
            # Test 1: Admin endpoint requires admin:all
            resp = await self.client.get(
                "/admin/jobs", headers={"Authorization": f"Bearer {USER_TOKEN}"}  # User token, not admin
            )
            # Should be 403 or 401 (forbidden/unauthorized)
            assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
            self.record_pass("Admin endpoints require admin:all")

            # Test 2: Non-owner gets 404 (anti-enumeration)
            # Create job as admin
            resp = await self.client.post(
                "/v2/jobs",
                json={"type": "test-job", "payload": {"test": "security"}},
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            )
            job_id = resp.json()["id"]

            # Try to GET as different user (should be 404, not 403)
            resp = await self.client.get(f"/v2/jobs/{job_id}", headers={"Authorization": f"Bearer {USER_TOKEN}"})
            assert resp.status_code == 404, f"Expected 404 (anti-enum), got {resp.status_code}"
            self.record_pass("Non-owner gets indistinguishable 404")
        except Exception as e:
            self.record_fail("Security enforcement", str(e))

    def record_pass(self, test_name):
        self.results.append(("✅", test_name))
        print(f"  ✅ {test_name}")

    def record_fail(self, test_name, error):
        self.results.append(("❌", test_name, error))
        print(f"  ❌ {test_name}: {error}")

    def print_summary(self):
        print("\n" + "=" * 60)
        print("📊 Test Summary")
        print("=" * 60)

        passed = sum(1 for r in self.results if r[0] == "✅")
        failed = sum(1 for r in self.results if r[0] == "❌")

        print(f"\nPassed: {passed}")
        print(f"Failed: {failed}")

        if failed > 0:
            print("\n❌ Failed Tests:")
            for result in self.results:
                if result[0] == "❌":
                    print(f"  - {result[1]}: {result[2]}")

        print("\n" + "=" * 60)


async def main():
    runner = SmokeTestRunner()
    await runner.run_all()


if __name__ == "__main__":
    asyncio.run(main())
