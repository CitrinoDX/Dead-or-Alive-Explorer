"""Dead or Alive Xtreme Beach Volleyball (Xbox): read straight from the disc image (or an extracted folder).
datadvd.afs: bodies v<code>NN.xpr (+.cat), menus/sprites.  datahdd.afs: swimsuits and accessories
md<item><wearer>.xpr (+.cat), stages, shops.  Costume XPRs are plain except for an overwritten magic dword.
Limbs are placed from the .cat bone map + the wearer's skeleton (v<wearer>.doax from the user's Team Ninja importer)."""
import os, re
from ..afs import Afs
from .. import vfs
from .base import Game, sort_key_label, NEED_SKELETONS
from . import xpr_mdl, cat_skel, gx_layout

NAMES = {
    "vks": "Kasumi", "vay": "Ayane", "vht": "Hitomi", "vhe": "Helena", "vcr": "Christie", "vle": "Lei Fang",
    "vls": "Lisa", "vtn": "Tina", "vpd": "Prairie dog", "vun": "Unknown",
}
BODY = re.compile(r"^(v[a-z]{2})(\d\d)\.xpr$", re.I)
ITEM = re.compile(r"^md(.+?)_?([a-z]{2})\.xpr$", re.I)
PLACES = ("stg", "shp", "etc", "fld")


class DOAX(Game):
    key = "doax"
    title = "Dead or Alive Xtreme Beach Volleyball"
    platform = "Xbox"
    hint = "the disc image (.iso) or an extracted folder with datadvd.afs / datahdd.afs"

    @classmethod
    def find_root(cls, folder):
        try:
            if vfs.is_disc_image(folder):
                src = vfs.XIso(folder)
            elif os.path.isdir(folder) and not os.path.exists(os.path.join(folder, "datahdd2.afs")):
                src = vfs.DirFS(folder)
            else:
                return None
            if not (src.exists("datadvd.afs") and src.exists("datahdd.afs")):
                return None
            with src.open("datadvd.afs") as f:
                return folder if Afs("datadvd.afs", f).find("vks00.xpr") is not None else None
        except (OSError, ValueError):
            return None

    def __init__(self, folder, names=None, sources=None):
        super().__init__(folder, names, sources)
        self.names = dict(NAMES, **(names or {}))
        self.src = vfs.open_source(folder)
        self.afs = {a: Afs(a, self.src.open(a)) for a in ("datadvd.afs", "datahdd.afs")}
        self.set_sources(self.sources)
        self.entries = {}
        for arch, afs in self.afs.items():
            for i, nm in enumerate(afs.names):
                if not nm or not nm.lower().endswith(".xpr"):
                    continue
                stem = nm[:-4]
                eid = stem.lower() if stem.lower() not in self.entries else "%s#%d" % (stem.lower(), i)
                cat = afs.find(stem + ".cat")
                e = dict(id=eid, archive=arch, index=i, cat=cat, size=afs.size(i), name=nm)
                b, it = BODY.match(nm), ITEM.match(nm)
                if b and b.group(1).lower() in self.names:
                    e.update(kind="body", char=b.group(1).lower(), label=b.group(2))
                elif it and "v" + it.group(2).lower() in self.names:
                    e.update(kind="item", char="v" + it.group(2).lower(), label=it.group(1))
                elif stem[:3].lower() in PLACES:
                    e.update(kind="place", char=None, label=stem)
                elif stem.lower().startswith("sp"):
                    e.update(kind="sprite", char=None, label=stem)
                else:
                    e.update(kind="other", char=None, label=stem)
                self.entries[eid] = e
        self._tree = None

    def set_sources(self, sources):
        super().set_sources(sources)
        self.layouts = gx_layout.LayoutFinder(sources.layout_dir("doax"), sources.alias_path("doax"))

    def tree(self):
        if self._tree is None:
            groups = []
            chars = sorted({e["char"] for e in self.entries.values() if e["char"]}, key=lambda c: self.names[c])
            for c in chars:
                for kind, what, lst in (("body", "bodies", False), ("item", "swimsuits & accessories", False)):
                    es = sorted((e for e in self.entries.values() if e["char"] == c and e["kind"] == kind),
                                key=lambda e: sort_key_label(e["label"]))
                    if es:
                        seen = {}
                        items = []
                        for e in es:   # some names occur twice in the archive: number the repeats
                            seen[e["label"]] = seen.get(e["label"], 0) + 1
                            lab = e["label"] if seen[e["label"]] == 1 else "%s (%d)" % (e["label"], seen[e["label"]])
                            items.append(dict(id=e["id"], label=lab, size=e["size"]))
                        groups.append(dict(title="%s - %s" % (self.names[c], what), list=lst, items=items))
            for kind, title in (("place", "Stages & places"), ("sprite", "Menus & sprites"), ("other", "Other resources")):
                es = sorted((e for e in self.entries.values() if e["kind"] == kind), key=lambda e: e["label"].lower())
                if es:
                    groups.append(dict(title=title, list=True, items=[dict(id=e["id"], label=e["label"], size=e["size"]) for e in es]))
            self._tree = groups
        return self._tree

    def load(self, sid):
        e = self.entries[sid]
        afs = self.afs[e["archive"]]
        who = self.names.get(e["char"], "")
        title = {"body": "%s body %s" % (who, e["label"]), "item": "%s - %s" % (who, e["label"])}.get(e["kind"], e["label"])
        sc, x = xpr_mdl.to_scene(sid, afs.read(e["index"]), title)
        sc.info["archive"] = "%s #%d (%s)" % (e["archive"], e["index"], e["name"])
        if x.objs and e["cat"] is not None:
            place_with_cat(sc, x, afs.read(e["cat"]), e["char"], self.sources.skeletons)
        if not sc.parts:
            path, note = self.layouts.find(sid, len(x.objs), len(x.textures)) if x.objs else (None, "")
            if path:
                gx_layout.place_parts(sc, gx_layout.parse_layout(path), len(x.objs))
                sc.note = note
            else:
                sc.default_parts()
                sc.note = "texture bundle (no meshes)" if not x.objs else (sc.note or "no .cat - parts shown at their stored origin")
        return sc


def place_with_cat(sc, x, cat_raw, char, skeleton_dir):
    """Shared by DOAX and the DOA3-era DOA2U costumes: .cat bone map + skeleton -> parts. Sets sc.note."""
    from . import xbox_crypt
    plain = xbox_crypt.decrypt_cat(cat_raw)
    if plain[:4] == b"\x01\0\0\0":
        sc.note = "newer .cat variant (not decoded yet) - parts shown at their stored origin"
        return
    try:
        c = cat_skel.parse_cat(plain)
    except ValueError as err:
        sc.note = "could not read .cat (%s) - parts shown at their stored origin" % err
        return
    bones = c.bones or (cat_skel.load_skeleton(char, c.version, skeleton_dir) if char else None)
    if not bones and not skeleton_dir:
        sc.note = "parts shown at their stored origin - " + NEED_SKELETONS
        return
    if not bones:
        sc.note = "no %s skeleton for '%s' - parts shown at their stored origin" % (cat_skel.VERSION_EXT.get(c.version, "?"), char)
        return
    n = cat_skel.place(sc, c, bones, len(x.objs))
    if not n:
        sc.parts = []
        sc.note = ".cat names no bones for these meshes - parts shown at their stored origin"
        return
    src = "embedded" if c.bones else "%s.%s" % (char, cat_skel.VERSION_EXT.get(c.version, "?"))
    sc.note = "placed from .cat + %s skeleton (%d of %d meshes)" % (src, n, sum(1 for g in sc.meshes if g))
