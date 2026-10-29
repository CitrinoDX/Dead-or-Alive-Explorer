"""Optional third-party data the viewer can use but does not ship: GreedXplorer's per-costume layouts, the Team Ninja
Blender importer's skeleton files and the 3ds Max layout scripts made for the DOAU Exporter's .3ds output. Users point
the viewer at their own copies (Setup panel or config.json)."""
import os, re

# game key -> GreedXplorer data subfolder
GX_SUBDIRS = {"doa2u": "doau2data", "doa1u": "doau1data", "doa3": "doa3data", "doax": "doaxdata"}
SKELETON_EXTS = (".doau", ".doa3", ".doax")
MAXSCRIPT = re.compile(r"^[a-z]{3}\d\d(\.3ds)?\.ms$", re.I)   # one per DOA2U costume: aya00.3ds.ms, kas00.ms


def maxscript_files(folder):
    """costume key -> path of every layout script under folder"""
    out = {}
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for f in sorted(files):
            if MAXSCRIPT.match(f):
                out.setdefault(f.split(".")[0].lower(), os.path.join(root, f))
    return out


def find_maxscripts(path):
    """The folder holding the DOA2U layout scripts (they sit in per-character subfolders): the deepest folder under path,
    at most three levels down, that contains them all."""
    if not path or not os.path.isdir(path):
        return None
    path = os.path.normpath(path)
    dirs = set()
    base = path.count(os.sep)
    for root, sub, files in os.walk(path):
        if root.count(os.sep) - base >= 3:
            sub[:] = []
        if any(MAXSCRIPT.match(f) for f in files):
            dirs.add(root)
    return os.path.commonpath(sorted(dirs)) if dirs else None


def find_greedxplorer(path):
    """The folder holding GreedXplorer's doau2data/doa3data/... folders: path itself or one level below it."""
    if not path or not os.path.isdir(path):
        return None
    cands = [path] + sorted(os.path.join(path, d) for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))
    for c in cands:
        if any(os.path.isdir(os.path.join(c, s)) for s in GX_SUBDIRS.values()):
            return c
    return None


def find_skeletons(path):
    """A folder of <code>.doau/.doa3/.doax skeleton files: path itself or its 'skeletons' subfolder."""
    if not path or not os.path.isdir(path):
        return None
    for c in (path, os.path.join(path, "skeletons")):
        if os.path.isdir(c) and any(f.lower().endswith(SKELETON_EXTS) for f in os.listdir(c)):
            return c
    return None


class Sources:
    def __init__(self, greedxplorer=None, skeletons=None, maxscripts=None):
        self.greedxplorer = find_greedxplorer(greedxplorer)
        self.skeletons = find_skeletons(skeletons)
        self.maxscripts = find_maxscripts(maxscripts)

    def layout_dir(self, key):
        """GreedXplorer layout folder for a game key, or None"""
        if not self.greedxplorer or key not in GX_SUBDIRS:
            return None
        d = os.path.join(self.greedxplorer, GX_SUBDIRS[key])
        return d if os.path.isdir(d) else None

    def alias_path(self, key):
        """GreedXplorer's mesh/texture-count signature table (objc2.ini) for a game key, or None"""
        d = self.layout_dir(key)
        if not d:
            return None
        for name in ("objc2.ini", "alias.txt"):
            p = os.path.join(d, name)
            if os.path.exists(p) and os.path.getsize(p):
                return p
        return None

    def summary(self):
        lay = {}
        for key in GX_SUBDIRS:
            d = self.layout_dir(key)
            lay[key] = sum(1 for f in os.listdir(d) if f.lower().endswith(".xml")) if d else 0
        skel = sum(1 for f in os.listdir(self.skeletons) if f.lower().endswith(SKELETON_EXTS)) if self.skeletons else 0
        return dict(greedxplorer=self.greedxplorer, layouts=lay, skeletons=self.skeletons, skeleton_files=skel,
                    maxscripts=self.maxscripts, maxscript_files=len(maxscript_files(self.maxscripts)) if self.maxscripts else 0)
