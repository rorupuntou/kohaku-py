"""Pytest integration for cross-client conformance suite."""

import pytest
from kohaku.conformance import (
    verify_all,
    verify_blinded_storage,
    verify_crypto_primitives,
    verify_invoices,
    verify_multishield_userop,
    verify_railgun,
    verify_tornado_notes,
)


def test_conformance_crypto_primitives():
    res = verify_crypto_primitives()
    assert res.passed is True, f"Crypto conformance failed: {res.errors}"
    assert res.cases_run > 0


def test_conformance_tornado_notes():
    res = verify_tornado_notes()
    assert res.passed is True, f"Tornado notes conformance failed: {res.errors}"
    assert res.cases_run > 0


def test_conformance_invoices():
    res = verify_invoices()
    assert res.passed is True, f"Invoices conformance failed: {res.errors}"
    assert res.cases_run > 0


def test_conformance_multishield_userop():
    res = verify_multishield_userop()
    assert res.passed is True, f"Multi-shield userop conformance failed: {res.errors}"
    assert res.cases_run > 0


def test_conformance_railgun():
    res = verify_railgun()
    assert res.passed is True, f"Railgun conformance failed: {res.errors}"
    assert res.cases_run > 0


def test_conformance_blinded_storage():
    res = verify_blinded_storage()
    assert res.passed is True, f"Blinded storage conformance failed: {res.errors}"
    assert res.cases_run > 0


def test_conformance_verify_all():
    results = verify_all()
    assert len(results) == 6
    for suite_name, res in results.items():
        assert res.passed is True, f"Suite '{suite_name}' failed: {res.errors}"
