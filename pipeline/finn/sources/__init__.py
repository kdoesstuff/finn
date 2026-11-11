"""Fetchers for every outside source FINN reads. Network code lives here and nowhere else.

NSE answers only from some networks (GitHub's runners and ordinary home connections, not the
assistant's sandboxes), so everything in this package is exercised offline against recorded
responses in tests/fixtures, and live by the manual `smoke-sources` workflow.
"""
