"""AIOS Kernel — the owned operating-system primitives.

Everything else in AIOS-0X registers with this kernel. The kernel owns:
identity, capabilities, state machines, authority, receipts, provenance,
promotion, rollback, and the adapter registry. It knows nothing about trading.
"""
