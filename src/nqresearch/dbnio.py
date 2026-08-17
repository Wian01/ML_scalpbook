"""Read-only helpers for Databento DBN files.

Raw vendor files are immutable; nothing in this module may open a raw file for
writing (canonical spec section 11).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
from databento import DBNStore

DEFAULT_CHUNK_ROWS = 2_000_000


def read_metadata(path: Path):
    """Return DBN metadata without decoding record data."""
    return DBNStore.from_file(str(path)).metadata


def iter_ndarray_chunks(path: Path, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> Iterator[np.ndarray]:
    """Yield structured-array chunks of a DBN file, bounded in memory."""
    store = DBNStore.from_file(str(path))
    yield from store.to_ndarray(count=chunk_rows)


def read_ndarray(path: Path) -> np.ndarray:
    """Read an entire (small) DBN file into one structured array."""
    store = DBNStore.from_file(str(path))
    return store.to_ndarray()
