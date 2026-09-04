"""Evaluation harness (spec §33). Separate from tests/: measures model + extraction
quality against golden data. Metrics below target do not fail CI (V0 thresholds are
advisory) — but a regression vs the stored baseline is flagged."""
