# Load Test Report — V16.0

**Environment:** Windows Server, SQLite WAL, local execution  
**Date:** 2026-07-03  
**Dataset:** Development database (moderate row counts)

---

## Methodology

Lightweight smoke load (50 iterations) — not full stress testing. For production sign-off, run dedicated tools (locust/k6) against Nginx HTTPS endpoint.

---

## Results

| Operation | Avg latency | Target | Status |
|-----------|------------:|--------|--------|
| API `GET /health` (50 req) | ~8.5 ms | < 200 ms | PASS |
| DB `get_customers()` (50 req) | ~0.1 ms | < 100 ms | PASS |
| Health Check 2.0 full suite | ~45 s | < 120 s | PASS |
| Portal security tests (6) | ~65 s | < 180 s | PASS |

*Exact numbers vary by hardware; re-run benchmark on target server.*

---

## Recommendations for production load

1. Deploy PostgreSQL when concurrent users exceed ~25
2. Enable Nginx `limit_req` on `/api/v1/auth/token`
3. Run job worker on schedule (not inline with UI)
4. Index review on `company_id` + date columns at scale
5. Full locust scenario: 100 concurrent API reads, 10 writes

---

## Verdict

**Baseline load:** acceptable for pilot / SME deployment.  
**Enterprise scale:** requires PostgreSQL + dedicated API workers + load test sign-off.
