"""Sealed pre-trade authorization envelopes (vNext goal G140).

The risk firewall answers "should this strategy trade". The envelope answers
the narrower question execution must ask: "was *this* order authorized, for
*this* instrument, in *this* size, and is that permission still live".

An envelope is minted only by :func:`core.capital_firewall.issue`, which holds
the HMAC secret. This module carries no signing key and offers no minting path:
constructing an :class:`AuthorizationEnvelope` directly produces fields without
a valid signature, and :meth:`AuthorizationEnvelope.verify` recomputes the
HMAC from the stored fields, so a forged or edited envelope never verifies
without the secret. Execution imports this module to *check* envelopes, never
to create them.

Enforced by ``tests/test_authorization_envelope.py``.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

__all__ = ["AuthorizationEnvelope"]


def _canonical_float(value: float) -> str:
    """Deterministic rendering of a float for the signed payload.

    ``repr`` round-trips the binary value exactly, so the signer and the
    verifier compute over the same bytes regardless of platform formatting.
    """
    return repr(float(value))


class AuthorizationEnvelope(BaseModel):
    """A sealed, expiring permission to trade one instrument up to a size.

    Frozen: editing a field after issuance invalidates the signature rather
    than moving the permission, because the signature covers every field a
    reader acts on. A narrowed permission is a new object from
    :meth:`apply_reduction`, re-signed by the holder of the secret.
    """

    model_config = {"frozen": True}

    envelope_id: str = Field(..., min_length=1)
    strategy_id: str = Field(..., min_length=1)
    strategy_version: str = Field(..., min_length=1)
    client_order_id: str = Field(..., min_length=1)
    instrument_id: str = Field(..., min_length=1)
    max_quantity: float = Field(...)
    max_notional_usd: float = Field(...)
    issued_at: datetime = Field(...)
    expires_at: datetime = Field(...)
    issuer: str = Field(..., min_length=1)
    signature: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _check_interval(self) -> AuthorizationEnvelope:
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")
        return self

    def canonical_payload(self) -> str:
        """The exact bytes (as text) the signature covers."""
        return "|".join(
            [
                self.envelope_id,
                self.strategy_id,
                self.strategy_version,
                self.client_order_id,
                self.instrument_id,
                _canonical_float(self.max_quantity),
                _canonical_float(self.max_notional_usd),
                self.issued_at.isoformat(),
                self.expires_at.isoformat(),
                self.issuer,
            ]
        )

    @staticmethod
    def _sign(canonical: str, secret: str) -> str:
        return hmac.new(
            secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def verify(self, secret: str) -> bool:
        """Recompute the HMAC from the stored fields and compare.

        The comparison is always against a freshly computed digest, never
        between two stored values, so swapping in a second envelope's
        signature cannot pass.
        """
        if not secret or not self.signature:
            return False
        expected = self._sign(self.canonical_payload(), secret)
        return hmac.compare_digest(expected, self.signature)

    def apply_reduction(
        self,
        *,
        max_quantity: float | None = None,
        max_notional_usd: float | None = None,
        secret: str,
    ) -> AuthorizationEnvelope:
        """Return a narrowed copy re-signed with the same secret.

        Either bound may shrink; neither may grow. Growing a bound raises,
        because a wider permission than the one issued is a new permission,
        not a reduction of the old one. Execution may reduce an
        authorization, never increase it.
        """
        new_quantity = self.max_quantity if max_quantity is None else max_quantity
        new_notional = self.max_notional_usd if max_notional_usd is None else max_notional_usd
        if new_quantity <= 0 or new_notional <= 0:
            raise ValueError("reduced bounds must stay positive")
        if new_quantity > self.max_quantity:
            raise ValueError(
                f"cannot widen max_quantity {self.max_quantity!r} to {new_quantity!r}"
            )
        if new_notional > self.max_notional_usd:
            raise ValueError(
                f"cannot widen max_notional_usd {self.max_notional_usd!r} to {new_notional!r}"
            )
        if not secret:
            raise ValueError("a secret is required to seal the reduced envelope")
        candidate = AuthorizationEnvelope(
            envelope_id=self.envelope_id,
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            client_order_id=self.client_order_id,
            instrument_id=self.instrument_id,
            max_quantity=new_quantity,
            max_notional_usd=new_notional,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
            issuer=self.issuer,
            signature="placeholder",
        )
        return candidate.model_copy(
            update={"signature": self._sign(candidate.canonical_payload(), secret)}
        )

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
