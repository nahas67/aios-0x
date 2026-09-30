"""Authorization envelopes seal size, instrument, and expiry (goal G140).

The defect this suite exists to prevent is an execution path that mints its
own permission: if the envelope can be forged, edited, replayed past expiry,
or widened after issuance, the capital firewall is advice rather than control.
Every test therefore attacks the seal from one direction and asserts the
attack fails.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from core.authorization import AuthorizationEnvelope
from core.capital_firewall import issue

SEAL_A = "firewall-test-seal-001"
SEAL_B = "a-different-test-seal"
T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def _envelope(**overrides) -> AuthorizationEnvelope:
    params = {
        "strategy_id": "momentum-1",
        "strategy_version": "v1",
        "client_order_id": "ord-001",
        "instrument_id": "inst-acme",
        "max_quantity": 10.0,
        "max_notional_usd": 90.0,
        "issuer": "capital-firewall",
        "secret": SEAL_A,
        "issued_at": T0,
        "ttl_seconds": 300.0,
        "envelope_id": "env-test-001",
    }
    params.update(overrides)
    return issue(**params)  # type: ignore[arg-type]


def test_a_freshly_issued_envelope_verifies() -> None:
    """The honest path works, or nothing downstream can be tested."""
    assert _envelope().verify(SEAL_A) is True


def test_a_forged_signature_does_not_verify() -> None:
    """An execution path that invents a permission must not pass the firewall.

    The signature is recomputed from the stored fields, so a copied signature
    from nowhere matches nothing.
    """
    envelope = _envelope()
    forged = envelope.model_copy(update={"signature": "0" * 64})
    assert forged.verify(SEAL_A) is False


def test_tampering_with_quantity_breaks_the_seal() -> None:
    """Editing an issued field invalidates the permission instead of moving it.

    A widened quantity with the old signature is exactly the forgery the HMAC
    exists to catch.
    """
    envelope = _envelope()
    tampered = envelope.model_copy(update={"max_quantity": 999.0})
    assert tampered.verify(SEAL_A) is False


def test_tampering_with_the_instrument_breaks_the_seal() -> None:
    """Replaying an envelope across instruments is a scope forgery, not reuse."""
    envelope = _envelope()
    tampered = envelope.model_copy(update={"instrument_id": "inst-other"})
    assert tampered.verify(SEAL_A) is False


def test_the_wrong_seal_does_not_verify() -> None:
    """A signature is only meaningful under the value that made it."""
    assert _envelope().verify(SEAL_B) is False


def test_an_empty_seal_never_verifies() -> None:
    """No signing value, no permission — an unconfigured verifier fails closed."""
    assert _envelope().verify("") is False


def test_reduction_narrows_quantity_and_stays_sealed() -> None:
    """Execution may reduce an authorization, and the reduced form still proves it."""
    envelope = _envelope()
    reduced = envelope.apply_reduction(max_quantity=4.0, secret=SEAL_A)
    assert reduced.max_quantity == 4.0
    assert reduced.max_notional_usd == envelope.max_notional_usd
    assert reduced.verify(SEAL_A) is True


def test_reduction_narrows_notional_and_stays_sealed() -> None:
    """The notional bound narrows independently of the quantity bound."""
    envelope = _envelope()
    reduced = envelope.apply_reduction(max_notional_usd=25.0, secret=SEAL_A)
    assert reduced.max_notional_usd == 25.0
    assert reduced.verify(SEAL_A) is True


def test_reduction_that_widens_quantity_raises() -> None:
    """A wider permission than the one issued is a new permission, not a reduction."""
    envelope = _envelope()
    with pytest.raises(ValueError, match="cannot widen max_quantity"):
        envelope.apply_reduction(max_quantity=envelope.max_quantity + 1.0, secret=SEAL_A)


def test_reduction_that_widens_notional_raises() -> None:
    """The notional direction is guarded the same way as the quantity direction."""
    envelope = _envelope()
    with pytest.raises(ValueError, match="cannot widen max_notional_usd"):
        envelope.apply_reduction(
            max_notional_usd=envelope.max_notional_usd + 1.0, secret=SEAL_A
        )


def test_reduction_to_a_non_positive_bound_raises() -> None:
    """A narrowed permission must still describe a trade that can happen."""
    envelope = _envelope()
    with pytest.raises(ValueError, match="must stay positive"):
        envelope.apply_reduction(max_quantity=0.0, secret=SEAL_A)


def test_an_envelope_is_frozen_after_issuance() -> None:
    """Sealed means sealed: field assignment after issuance is unconstructible."""
    envelope = _envelope()
    with pytest.raises(ValidationError, match="frozen"):
        envelope.max_quantity = 1.0  # type: ignore[misc]


def test_expiry_is_after_issuance_by_the_ttl() -> None:
    """The TTL is the lifetime of the permission, not a suggestion attached later."""
    envelope = _envelope(ttl_seconds=60.0)
    assert envelope.expires_at == T0 + timedelta(seconds=60)


def test_a_non_positive_ttl_is_refused_at_issuance() -> None:
    """An envelope that is already expired, or never expires, must never be minted."""
    with pytest.raises(ValueError, match="ttl_seconds must be positive"):
        _envelope(ttl_seconds=0.0)


def test_minting_without_a_signing_value_is_refused() -> None:
    """An unsigned envelope must not exist, even briefly."""
    with pytest.raises(ValueError, match="secret is required"):
        _envelope(secret="")


def test_an_inverted_interval_is_refused_by_the_model() -> None:
    """Expiry before issuance is a contradiction, not a short lifetime."""
    with pytest.raises(ValidationError, match="expires_at must be after issued_at"):
        AuthorizationEnvelope(
            envelope_id="env-bad",
            strategy_id="s",
            strategy_version="v1",
            client_order_id="o",
            instrument_id="i",
            max_quantity=1.0,
            max_notional_usd=10.0,
            issued_at=T0,
            expires_at=T0 - timedelta(seconds=1),
            issuer="x",
            signature="y",
        )
