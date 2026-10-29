"""Registry of supported games. Each module exposes a Game subclass (see base.py)."""
from .doa1u import DOA1U
from .doa2u import DOA2U
from .doa3 import DOA3
from .doax import DOAX
from .doax2 import DOAX2
from .doa4 import DOA4

GAMES = [DOA1U, DOA2U, DOA3, DOA4, DOAX, DOAX2]
BY_KEY = {g.key: g for g in GAMES}
# the game picker's fixed order; every game is listed, greyed out until it is added (or, for PLANNED, supported)
ORDER = ["doa1u", "doa2u", "doa3", "doa4", "doax", "doax2"]
PLANNED = {}
