"""Registry of supported games. Each module exposes a Game subclass (see base.py)."""
from .doa1u import DOA1U
from .doa2u import DOA2U
from .doax import DOAX
from .doax2 import DOAX2
from .doa4 import DOA4

GAMES = [DOA2U, DOA1U, DOAX, DOAX2, DOA4]
BY_KEY = {g.key: g for g in GAMES}
