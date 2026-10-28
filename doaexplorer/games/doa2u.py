"""Dead or Alive 2 Ultimate (Xbox): costumes, stages and other XPRs from datahdd2/datadvd/datahdd.afs."""
import os, re
from ..afs import Afs
from ..scene import Scene
from .base import Game, sort_key_label, NEED_GX
from . import xpr_mdl, gx_layout
from . import cat_skel
from .doax import place_with_cat, cat_skeleton

NAMES = {  # extras from the Team Ninja importer's skeleton notes; hik/sui/gok/sam/nin are DOA3-era models
    "kas": "Kasumi", "aya": "Ayane", "tin": "Tina", "lei": "Lei Fang", "hel": "Helena",
    "zac": "Zack", "jan": "Jann Lee", "ryu": "Ryu Hayabusa", "gen": "Gen Fu", "leo": "Leon",
    "bas": "Bass", "bay": "Bayman", "ein": "Ein", "tng": "Tengu", "pdg": "Prairie dog",
    "kor": "Hitomi", "yti": "Tina (young)", "wba": "Bass (young)", "mam": "Helena's mother", "lor": "Lorraine",
    "hks": "Kasumi clone", "hik": "Helena (DOA3)", "sui": "Brad Wong", "gok": "Christie", "sam": "Bayman (DOA3)",
    "nin": "Hayate", "efc": "Effects",
}

ARCHIVES = ("datahdd2.afs", "datadvd.afs", "datahdd.afs")   # first hit wins for duplicated names
COSTUME = re.compile(r"^([A-Za-z]{3})([A-Za-z]?\d+)\.xpr$")


class DOA2U(Game):
    key = "doa2u"
    title = "Dead or Alive 2 Ultimate"
    platform = "Xbox"
    hint = "the game folder (or its DOA2 subfolder) with datahdd2.afs / datadvd.afs / datahdd.afs"

    @classmethod
    def find_root(cls, folder):
        for f in (folder, os.path.join(folder, "DOA2")):
            if any(os.path.exists(os.path.join(f, a)) for a in ARCHIVES):
                return f
        return None

    def __init__(self, folder, names=None, sources=None):
        super().__init__(folder, names, sources)
        self.names = dict(NAMES, **(names or {}))
        self.afs = {a: Afs(os.path.join(folder, a)) for a in ARCHIVES if os.path.exists(os.path.join(folder, a))}
        self.set_sources(self.sources)
        self.entries = {}
        for arch, afs in self.afs.items():
            for i, nm in enumerate(afs.names):
                if not nm or not nm.lower().endswith(".xpr"):
                    continue
                m = COSTUME.match(nm)
                if nm.lower().startswith("stage_"):
                    kind, char, label = "stage", "stage", nm[6:-4]
                elif m and not nm.lower().startswith("sp"):
                    kind, char, label = "costume", m.group(1).lower(), m.group(2).upper()
                else:
                    kind, char, label = "other", "other", nm[:-4]
                eid = nm[:-4].lower()
                if eid in self.entries:
                    continue
                self.entries[eid] = dict(id=eid, kind=kind, char=char, label=label, archive=arch, index=i,
                                         size=afs.size(i), cat=afs.find(nm[:-4] + ".cat"))
        self._tree = None

    def set_sources(self, sources):
        super().set_sources(sources)
        self.layouts = gx_layout.LayoutFinder(sources.layout_dir("doa2u"), sources.alias_path("doa2u"))
        # the 'A#' costumes are DOA3 models: each matches a DOA3 costume's mesh + texture count exactly
        self.doa3_layouts = gx_layout.LayoutFinder(sources.layout_dir("doa3"), sources.alias_path("doa3"))

    def tree(self):
        if self._tree is None:
            chars = {}
            for e in self.entries.values():
                if e["kind"] == "costume":
                    chars.setdefault(e["char"], []).append(e)
            groups = []
            for code, es in sorted(chars.items(), key=lambda kv: self.names.get(kv[0], kv[0].upper())):
                es.sort(key=lambda e: sort_key_label(e["label"]))
                groups.append(dict(title="%s (%s)" % (self.names.get(code, code.upper()), code), list=False,
                                   items=[dict(id=e["id"], label=e["label"], size=e["size"]) for e in es]))
            for kind, title in (("stage", "Stages"), ("other", "Other resources")):
                es = sorted((e for e in self.entries.values() if e["kind"] == kind), key=lambda e: e["label"].lower())
                if es:
                    groups.append(dict(title=title, list=True,
                                       items=[dict(id=e["id"], label=e["label"], size=e["size"]) for e in es]))
            self._tree = groups
        return self._tree

    def load(self, sid):
        e = self.entries[sid]
        raw = self.afs[e["archive"]].read(e["index"])
        title = "%s %s" % (self.names.get(e["char"], e["char"].upper()), e["label"]) if e["kind"] == "costume" else e["label"]
        sc, x = xpr_mdl.to_scene(sid, raw, title)
        sc.info["archive"] = e["archive"]
        if e["kind"] == "costume" and x.compact and sid not in self.layouts.files:
            # DOA3-era model: limb numbering differs from the regular costumes, so use the matching DOA3 layout
            path, note = self.doa3_layouts.find(sid, len(x.objs), len(x.textures))
            if path and "same mesh/texture count" in note:
                gx_layout.place_parts(sc, gx_layout.parse_layout(path), len(x.objs))
                sc.note = "DOA3 model: layout %s from GreedXplorer's DOA3 set (same mesh and texture count)" % os.path.basename(path)
                self._skeleton(sc, e, 3)
            elif e["cat"] is not None:
                place_with_cat(sc, x, self.afs[e["archive"]].read(e["cat"]), e["char"], self.sources.skeletons)
            if not sc.parts:
                sc.default_parts()
                sc.note = ("DOA3-era costume without a matching layout - parts shown at their stored origin"
                           if self.sources.greedxplorer else "parts shown at their stored origin - " + NEED_GX)
        elif e["kind"] == "costume":
            path, note = self.layouts.find(sid, len(x.objs), len(x.textures))
            sc.note = note
            if path:
                gx_layout.place_parts(sc, gx_layout.parse_layout(path), len(x.objs))
                if sc.parts:
                    self._skeleton(sc, e, 2)
            if not sc.parts:
                sc.default_parts()
                if not path:
                    sc.note = ("no layout available - parts shown at their stored origin" if self.sources.greedxplorer
                               else "parts shown at their stored origin - " + NEED_GX)
        else:
            sc.default_parts()
            if not x.objs:
                sc.note = "texture bundle (no meshes)"
        return sc

    def _skeleton(self, sc, e, version):
        """Layout-placed costumes: the character's skeleton for the skeleton view. The importer's skeleton files put
        the joints within a few millimetres of GreedXplorer's limb positions."""
        cat = self.afs[e["archive"]].read(e["cat"]) if e["cat"] is not None else None
        bones, src = cat_skeleton(cat, e["char"], self.sources.skeletons, version)
        if bones:
            cat_skel.add_skeleton(sc, bones, src)
