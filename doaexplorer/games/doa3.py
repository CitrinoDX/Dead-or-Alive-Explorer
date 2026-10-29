"""Dead or Alive 3 (Xbox): read straight from the disc image (or an extracted folder). Everything sits in
loadfile.afs: per character <name>.bin / .mot, a sprite.xpr (name plate and icon) and the costumes <code><nn>.xpr
(+ .cat); stages stg<XXX>.xpr (+ s<XXX>_dat.bin), effects efc0.xpr and the menu sprite.xpr bundles.
All XPRs are plain XPR0 with the compact MDL layout. Costume limbs are stored around their own pivots, each along its
own Z axis: the .cat (cat3.py) names each limb's bone and gives the bind rotations, and default.xbe holds every
character's skeleton. Hair and cloth pieces moved by the physics are placed from GreedXplorer's DOA3 layouts when
the user has them (matched by name, else by mesh and texture count). Stages are stored in world space."""
import os, re
import numpy as np
from ..afs import Afs
from .. import vfs
from .base import Game, sort_key_label
from ..scene import Scene
from . import xpr_mdl, gx_layout, cat_skel, cat3

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
# default.xbe's skeleton table, one record per character in this order: 17 (x, y, z, 0) offsets, bones 0-14 then the
# eyes (the Team Ninja importer's .doa3 files are copies of it). A 21st, partial record (Raidou) follows.
XBE_ORDER = ("zac", "tin", "jan", "kte", "ryu", "kas", "gen", "hik", "bay", "bas", "nin", "lei", "aya", "kor", "tng",
             "bni", "sui", "gok", "chi", "sam")
XBE_RECORD = 68   # dwords


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
        self._skeletons = None

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

    def skeleton(self, char):
        """(24 bone offsets or None, where they came from): default.xbe's table, else the user's importer file"""
        if self._skeletons is None:
            try:
                with self.src.open("default.xbe") as f:
                    self._skeletons = xbe_skeletons(f.read())
            except (OSError, ValueError):
                self._skeletons = {}
        if char in self._skeletons:
            return self._skeletons[char], "default.xbe"
        bones = cat_skel.load_skeleton(char, 3, self.sources.skeletons) if self.sources.skeletons else None
        return bones, "%s.doa3" % char

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
            self.assemble(sc, x, e)
        elif e["kind"] == "stage":
            nfar = split_far(sc)
            if nfar:
                sc.note = "%d sky and far scenery pieces start hidden (Far scenery in the parts panel)" % nfar
        else:
            sc.default_parts()
            if not x.objs:
                sc.note = "texture bundle (no meshes)"
        return sc

    def assemble(self, sc, x, e):
        """Limbs, joints, eyes, low poly and shadow meshes from the .cat; copies of a placed mesh (the physics hair)
        hidden on it; the remaining hair and cloth pieces from GreedXplorer's layout, else hidden under Unassigned."""
        cat = None
        try:
            cat = cat3.parse(self.afs.read(e["cat"])) if e["cat"] is not None else None
        except ValueError:
            pass
        bones, src = self.skeleton(e["char"])
        placed, notes = set(), []
        if cat:
            if bones is not None:
                P, how = cat3.skeleton_positions(bones), "the skeleton in " + src
            else:
                P = cat3.joint_skeleton(cat, {i: ob.positions[0] for i, ob in enumerate(x.objs) if 0 in ob.positions})
                how = "its joints alone (no eyes, and no hands without wrist joints)"
            placed = cat3.place(sc, cat, P, len(x.objs))
            notes.append("placed from the .cat and " + how)
        placed |= place_copies(sc, placed)
        path, note = self.layouts.find(e["id"], len(x.objs), len(x.textures))
        if path:
            gs = Scene(e["id"])
            gs.meshes = sc.meshes
            gx_layout.place_parts(gs, gx_layout.parse_layout(path), len(x.objs))
            if not placed:
                sc.parts = gs.parts
                hide_copies(sc)
                notes.append(note)
                more = gs.parts
            else:
                # its hand-placed pieces; the pieces it spreads out in a row (Misc 'OBJ_n') are no better than none
                more = [p for p in gs.parts if p["mesh"] not in placed and (p["group"] == "Character" or p["visible"])]
                sc.parts += more
                if more:
                    notes.append("%d more from GreedXplorer's %s" % (len({p["mesh"] for p in more}),
                                                                      os.path.basename(path)))
            placed |= {p["mesh"] for p in more}
        if not placed:
            sc.default_parts()
            sc.note = "no .cat or layout - parts shown at their stored origin"
            return
        left = [i for i, g in enumerate(sc.meshes) if g is not None and i not in placed]
        for i in left:
            sc.add_part(sc.meshes[i].get("name") or "OBJ_%d" % i, i, None, "Unassigned", visible=False)
        if left:
            notes.append("%d meshes the .cat doesn't place (physics hair and cloth, a coarser set of limbs) hidden "
                         "under Unassigned" % len(left))
        if bones is not None:
            cat_skel.add_skeleton(sc, bones, src)
        sc.note = "; ".join(notes)


def xbe_skeletons(xbe):
    """char code -> 24 bone offsets from default.xbe's skeleton table, found by its shape: the hips record is zero,
    the right foot repeats the left, the right forearm mirrors the left, and records follow every XBE_RECORD dwords"""
    a = np.frombuffer(xbe, "<u4", len(xbe) // 4)
    f = a.view("<f4")
    n = len(a) - XBE_RECORD
    if n <= 0:
        return {}
    s, t = (lambda k: a[k:k + n]), (lambda k: f[k:k + n])
    ok = (s(3) == 0) & (s(7) == 0) & (s(8) == 0) & (s(9) == 0) & (s(10) == 0) & (s(11) == 0)
    ok &= (s(36) == s(12)) & (s(37) == s(13)) & (s(38) == s(14)) & (t(16) > 0.1) & (t(40) == -t(16))
    cand = set(np.nonzero(ok)[0].tolist())
    best = []
    for c in sorted(cand):
        if c - XBE_RECORD in cand:
            continue
        run = [c]
        while run[-1] + XBE_RECORD in cand:
            run.append(run[-1] + XBE_RECORD)
        best = max(best, run, key=len)
    if len(best) < len(XBE_ORDER):
        return {}
    out = {}
    for code, c in zip(XBE_ORDER, best):
        r = f[c:c + XBE_RECORD].reshape(17, 4)[:, :3].astype(np.float64)
        bones = np.zeros((24, 3))
        bones[:15], bones[cat3.EYE_BONES[0]], bones[cat3.EYE_BONES[1]] = r[:15], r[15], r[16]
        out[code] = bones
    return out


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


def shown_vertices(sc):
    """mesh -> (its first visible Character part, its vertex set)"""
    shown = {}
    for p in sc.parts:
        if p["group"] == "Character" and p["visible"] and sc.meshes[p["mesh"]] is not None:
            shown.setdefault(p["mesh"], (p, {tuple(v) for v in np.round(sc.meshes[p["mesh"]]["pos"], 5)}))
    return shown


def copy_of(shown, sc, mesh):
    """the part showing a mesh that contains every vertex of this one, or None"""
    verts = {tuple(v) for v in np.round(sc.meshes[mesh]["pos"], 5)}
    return next((p for m, (p, vs) in shown.items() if m != mesh and verts <= vs), None)


def place_copies(sc, placed):
    """The physics hair of most costumes is an exact copy of the hair inside the head mesh: put a mesh the .cat leaves
    over on the part that shows all its vertices, hidden. Returns the meshes it placed."""
    shown, out = shown_vertices(sc), set()
    for i, g in enumerate(sc.meshes):
        if g is not None and i not in placed:
            p = copy_of(shown, sc, i)
            if p is not None:
                sc.add_part("%s (copy)" % (g.get("name") or "OBJ_%d" % i), i, p["m"], p["group"], visible=False)
                out.add(i)
    return out


def hide_copies(sc):
    """Kasumi's and Ayane's layouts list a 'hair' mesh in Misc with no position, so it would show at the hips. It is
    an exact copy of the hair inside the head mesh: hide a visible unplaced Misc part whose vertices all occur in a
    mesh the Character group already shows."""
    shown = shown_vertices(sc)
    for p in sc.parts:
        g = sc.meshes[p["mesh"]]
        if p["group"] != "Misc" or not p["visible"] or g is None or not np.allclose(p["m"], np.eye(4)):
            continue
        if copy_of(shown, sc, p["mesh"]) is not None:
            p["visible"] = False
            p["name"] += " (copy)"
