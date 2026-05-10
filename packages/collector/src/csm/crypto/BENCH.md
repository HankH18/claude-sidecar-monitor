# Encryption overhead benchmark

Per docs/spec.md §10 risk #1 and the T29 acceptance criteria, SQLCipher overhead must stay ≤10% on a representative workload.

## Methodology

`tests/crypto/test_overhead.py` (run with `uv run pytest -m bench`):

1. Set up two SQLite databases — one plain, one SQLCipher with a 32-byte key derived via the production `KdfParams`.
2. Apply the same migration to both.
3. Insert 1,000 transcript_message rows of representative size (≈1 KB body each, with `usage` token fields populated).
4. Run 100 token-aggregation passes (`SELECT SUM(input_tokens), SUM(output_tokens), …`).
5. Time both databases. Record `(insert_total, agg_total, total)` for each.

Pass criterion: `(encrypted_total - plain_total) / plain_total ≤ 0.10`.

## Reference numbers (will be regenerated at release)

| Workload | Plain SQLite (ms) | SQLCipher (ms) | Overhead |
|---|---|---|---|
| 1,000 transcript inserts | TBD | TBD | TBD |
| 100 aggregation passes   | TBD | TBD | TBD |
| Total                    | TBD | TBD | TBD |

Re-run with `make bench` (alias to `uv run pytest -m bench --benchmark` in `packages/collector/`).

## Notes

- The Argon2id KDF runs **once** at startup (key cached in Keychain), so it does not factor into per-query overhead. Its cost (~200 ms on Apple Silicon at the production parameters) is amortized across the daemon's lifetime.
- SQLCipher uses AES-256-CBC + HMAC-SHA512 per page. Per-query cost is dominated by I/O, not crypto.
- WAL mode + `cipher_page_size=4096` (default) align with SQLite's natural page size on macOS and minimize encryption overhead on transcript inserts.
