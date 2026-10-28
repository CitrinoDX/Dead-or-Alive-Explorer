"""What every game module provides to the server."""
from ..sources import Sources


class Game:
    key = ""          # short id used in URLs and config.json
    title = ""
    platform = ""
    hint = ""         # what to point the viewer at, shown in Setup

    def __init__(self, folder, names=None, sources=None):
        self.folder = folder
        self.sources = sources or Sources()

    def set_sources(self, sources):
        """Called when the user changes the GreedXplorer / skeleton folders."""
        self.sources = sources

    @classmethod
    def find_root(cls, folder):
        """Return the folder this game should read (folder itself or a known subfolder), or None."""
        raise NotImplementedError

    def tree(self):
        """[{title, items:[{id, label, size}], list: bool}] - groups shown in the sidebar."""
        raise NotImplementedError

    def load(self, sid):
        """-> Scene"""
        raise NotImplementedError

    def summary(self):
        n = sum(len(g["items"]) for g in self.tree())
        return "%d entries" % n


def sort_key_label(label):
    """numbers first in numeric order, then the rest alphabetically"""
    s = str(label)
    return (not s.isdigit(), int(s) if s.isdigit() else 0, s.lower())


NEED_GX = "add your GreedXplorer folder in Setup to assemble the limbs"
NEED_SKELETONS = "add the Team Ninja importer's skeletons folder in Setup to assemble the limbs"
