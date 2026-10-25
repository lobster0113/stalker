"""Gate A spot set: fixed, versioned preflop push/fold and all-in-call spots (see referee/GATES.md)."""
from .spots import SPOT_SET_VERSION, SPOTS_V1, SpotSetError, load_spots, spot_set_hash

__all__ = ["SPOT_SET_VERSION", "SPOTS_V1", "SpotSetError", "load_spots", "spot_set_hash"]
