"""Monotonic edit ordering shared by graph and annotation histories."""
from __future__ import annotations

import itertools


_SEQUENCES = itertools.count(1)


def next_edit_sequence() -> int:
    """Return a process-local sequence number for one committed user edit."""
    return next(_SEQUENCES)


__all__ = ["next_edit_sequence"]
