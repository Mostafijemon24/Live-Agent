"""Phase 3 agent engine.

Model output is untrusted input. Nothing in this package lets text produced by a
model decide permissions, approval requirements, destinations or data scope:
those are derived on the server from the tool registry, the workspace policy and
the stored records, and re-checked right before every execution.
"""
