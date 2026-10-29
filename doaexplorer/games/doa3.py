"""Dead or Alive 3 (Xbox): read straight from the disc image (or an extracted folder). Everything sits in
loadfile.afs: per character <name>.bin / .mot, a sprite.xpr (name plate and icon) and the costumes <code><nn>.xpr
(+ .cat); stages stg<XXX>.xpr (+ s<XXX>_dat.bin), effects efc0.xpr and the menu sprite.xpr bundles.
All XPRs are plain XPR0 with the compact MDL layout. Costume limbs are stored around their own pivots and are placed
with GreedXplorer's DOA3 layouts (matched by name, else by mesh and texture count); the .cat files are the newer
variant (dword0 = 1) and are not decoded. Stages are stored in world space."""
import os, re
import numpy as np
from ..afs import Afs
from .. import vfs
from .base import Game, sort_key_label, NEED_GX
from . import xpr_mdl, gx_layout, cat_skel
from .doax import cat_skeleton

# from each character's name plate in its sprite.xpr. The file codes are older style names: karate = Ein,
# bayman = Leon (not playable in DOA3, but his three costumes are on the disc), sambo = Bayman, koryu = Hitomi,
# hika = Helena, suiken = Brad Wong, gokei = Christie, bosnin = Omega, chin = a second Gen Fu model.
NAMES = {
    "zac": "Zack", "tin": "Tina", "jan": "Jann Lee", "kte": "Ein", "ryu": "Ryu Hayabusa", "kas": "Kasumi",
    "gen": "Gen Fu", "hik": "Helena", "bay": "Leon", "bas": "Bass", "nin": "Hayate", "lei": "Lei Fang",
    "aya": "Ayane", "kor": "Hitomi", "bni": "Omega", "sui": "Brad Wong", "gok": "Christie", "chi": "Gen Fu",
    "sam": "Bayman",
}
ARCHIVE = "loadfile.afs"
COSTUME = re.compile(r"^([a-z]{3})(\d\d)\.xpr$", re.I)
STAGE = re.compile(r"^stg(\w+)\.xpr$", re.I)


class DOA3(Game):
    key = "doa3"
    title = "Dead or Alive 3"
    platform = "Xbox"
    hint = "the disc image (.iso), or an extracted folder with loadfile.afs"

    @classmethod
    def find_root(cls, folder):
        try:
            if vfs.is_disc_image(folder):
                src = vfs.XIso(folder)
            elif os.path.isdir(folder):
                src = vfs.DirFS(folder)
            else:
                return None
            if not src.exists(ARCHIVE):
                return None
            with src.open(ARCHIVE) as f:
                return folder if Afs(ARCHIVE, f).find("kas00.xpr") is not None else None
        except (OSError, ValueError):
            return None

    def __init__(self, folder, names=None, sources=None):
        super().__init__(folder, names, sources)
        self.names = dict(NAMES, **(names or {}))
        self.src = vfs.open_source(folder)
        self.afs = Afs(ARCHIVE, self.src.open(ARCHIVE))
        self.set_sources(self.sources)
        self.entries = {}
        names_ = self.afs.names
        owner = None   # the character whose <name>.bin came last: its sprite.xpr is the name plate and icon
        for i, nm in enumerate(names_):
            if not nm:
                continue
            low = nm.lower()
            if low.endswith(".bin") and low != "dmy.bin" and i + 1 < len(names_) and (names_[i + 1] or "").endswith(".mot"):
                owner = i
            if not low.endswith(".xpr"):
                continue
            e = dict(index=i, size=self.afs.size(i), name=nm, cat=None, char=None)
            c, s = COSTUME.match(nm), STAGE.match(nm)
            if c and c.group(1).lower() in self.names:
                e.update(id=low[:-4], kind="costume", char=c.group(1).lower(), label=c.group(2),
                         cat=self.afs.find(nm[:-4] + ".cat"))
            elif s:
                e.update(id=low[:-4], kind="stage", label=s.group(1).upper())
            elif low == "sprite.xpr":
                code = self._next_costume_code(i)
                if owner is not None and i - owner <= 3 and code:
                    e.update(id="sprite_%d" % i, kind="sprite", label="%s - name plate and icon" % self.names[code])
                else:
                    e.update(id="sprite_%d" % i, kind="sprite", label="sprite #%d" % i)
            else:
                e.update(id=low[:-4], kind="other", label=nm[:-4])
            if e["id"] not in self.entries:
                self.entries[e["id"]] = e
        self._tree = None

    def _next_costume_code(self, i):
        """code of the first costume after entry i, if it comes before the next character's files"""
        for nm in self.afs.names[i + 1:i + 8]:
            m = COSTUME.match(nm or "")
            if m and m.group(1).lower() in self.names:
                return m.group(1).lower()
            if nm and nm.lower().endswith(".mot"):
                return None
        return None

    def set_sources(self, sources):
        super().set_sources(sources)
        self.layouts = gx_layout.LayoutFinder(sources.layout_dir("doa3"), sources.alias_path("doa3"))

    def tree(self):
        if self._tree is None:
            chars = {}
            for e in self.entries.values():
                if e["kind"] == "costume":
                    chars.setdefault(e["char"], []).append(e)
            groups = []
            for code, es in sorted(chars.items(), key=lambda kv: (self.names.get(kv[0], kv[0].upper()), kv[0])):
                es.sort(key=lambda e: sort_key_label(e["label"]))
                groups.append(dict(title="%s (%s)" % (self.names.get(code, code.upper()), code), list=False,
                                   items=[dict(id=e["id"], label=e["label"], size=e["size"]) for e in es]))
            for kind, title in (("stage", "Stages"), ("other", "Effects"), ("sprite", "Menus & sprites")):
                es = [e for e in self.entries.values() if e["kind"] == kind]
                es.sort(key=lambda e: e["index"] if kind == "sprite" else e["label"].lower())
                if es:
                    groups.append(dict(title=title, list=True,
                                       items=[dict(id=e["id"], label=e["label"], size=e["size"]) for e in es]))
            self._tree = groups
        return self._tree

    def load(self, sid):
        e = self.entries[sid]
        title = ("%s %s" % (self.names.get(e["char"], e["char"].upper()), e["label"]) if e["kind"] == "costume"
                 else "Stage " + e["label"] if e["kind"] == "stage" else e["label"])
        sc, x = xpr_mdl.to_scene(sid, self.afs.read(e["index"]), title)
        sc.info["archive"] = "%s #%d (%s)" % (ARCHIVE, e["index"], e["name"])
        if e["kind"] == "costume":
            path, note = self.layouts.find(sid, len(x.objs), len(x.textures))
            sc.note = note
            if path:
                gx_layout.place_parts(sc, gx_layout.parse_layout(path), len(x.objs))
                hide_copies(sc)
            if sc.parts:
                cat = self.afs.read(e["cat"]) if e["cat"] is not None else None
                bones, src = cat_skeleton(cat, e["char"], self.sources.skeletons, 3)
                if bones:
                    cat_skel.add_skeleton(sc, bones, src)
            else:
                sc.default_parts()
                sc.note = ("no layout available - parts shown at their stored origin" if self.sources.greedxplorer
                           else "parts shown at their stored origin - " + NEED_GX)
        elif e["kind"] == "stage":
            nfar = split_far(sc)
            if nfar:
                sc.note = "%d sky and far scenery pieces start hidden (Far scenery in the parts panel)" % nfar
        else:
            sc.default_parts()
            if not x.objs:
                sc.note = "texture bundle (no meshes)"
        return sc


FAR_GAP, FAR_SIZE = 100.0, 400.0   # stage units: the arenas span 10-100, sky domes and backdrops up to 47,000


def split_far(sc):
    """Stage parts, with the sky domes and distant backdrops in a hidden 'Far scenery' group so the view frames the
    arena: pieces whose box starts more than FAR_GAP from the stage centre or is wider than FAR_SIZE. That keeps
    57-100% of each stage's triangles in view. Returns the number of far pieces."""
    nfar = 0
    for i, g in enumerate(sc.meshes):
        if g is None:
            continue
        p = np.asarray(g["pos"], np.float64)
        lo, hi = p.min(0), p.max(0)
        far = np.linalg.norm(np.maximum(0, np.maximum(lo, -hi))) > FAR_GAP or np.linalg.norm(hi - lo) > FAR_SIZE
        sc.add_part(g.get("name") or "OBJ_%d" % i, i, None, "Far scenery" if far else "Stage", visible=not far)
        nfar += far
    return nfar


def hide_copies(sc):
    """Kasumi's and Ayane's layouts list a 'hair' mesh in Misc with no position, so it would show at the hips. It is
    an exact copy of the hair inside the head mesh: hide a visible unplaced Misc part whose vertices all occur in a
    mesh the Character group already shows."""
    shown = {}
    for p in sc.parts:
        if p["group"] == "Character" and p["visible"] and sc.meshes[p["mesh"]] is not None:
            shown.setdefault(p["mesh"], {tuple(v) for v in np.round(sc.meshes[p["mesh"]]["pos"], 5)})
    for p in sc.parts:
        g = sc.meshes[p["mesh"]]
        if p["group"] != "Misc" or not p["visible"] or g is None or not np.allclose(p["m"], np.eye(4)):
            continue
        verts = {tuple(v) for v in np.round(g["pos"], 5)}
        if any(verts <= vs for m, vs in shown.items() if m != p["mesh"]):
            p["visible"] = False
            p["name"] += " (copy)"
