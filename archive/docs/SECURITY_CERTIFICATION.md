# Security Certification — V17.3

**Generated:** 2026-07-02 11:12:18
**Tool:** `tools/generate_v17_3_certification.py`

## Summary

| Metric | Count |
|--------|------:|
| Pass | 8 |
| Fail | 0 |
| Pass rate | 100.0% |

## Verdict

**SECURITY CERTIFIED** — 8 pass, 0 fail.

## V17.3

All items normalized to **PASS** or **FAIL** only.

## Detailed Results

| Status | Category | Check | Detail |
|--------|----------|-------|--------|
| pass | Security | Argon2id hashing | database.hash_password |
| pass | Security | No SHA256 in hash_password |  |
| pass | Security | No admin123 on login |  |
| pass | Security | No session in URL |  |
| pass | Security | Password policy |  |
| pass | Security | Unauth blocked |  |
| pass | Security | JWT auth | {"access_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidXNlcm5hbW |
| pass | Security | Portal security suite | t PASS distributor cannot view internal nav PASS distributor order isolation PASS price list rate PASS portal order crea |