"""Dead or Alive 1 Ultimate (Xbox, bundled with DOA2U): loose XPR0 files in DOA1/data.
Costumes use the compact OBJ layout; .bin files that start with XPR0 are stages and UI bundles."""
import os, re
from .base import Game, sort_key_label, NEED_GX
from . import xpr_mdl, gx_layout

NAMES = {
    "kas": "Kasumi", "tin": "Tina", "lei": "Lei Fang", "zac": "Zack", "jan": "Jann Lee", "ryu": "Ryu Hayabusa",
    "gen": "Gen Fu", "rai": "Raidou", "sam": "Bayman",   # 'sam' is Bayman in the Team Ninja skeleton notes
}
COSTUME = re.compile(r"^([a-z]{3})(\d\d)\.xpr$", re.I)
STAGE_HINT = ("hasi", "shi", "tera", "way", "hama", "kaku", "nway", "west", "ele", "rai1", "terab")


class DOA1U(Game):
    key = "doa1u"
    title = "Dead or Alive 1 Ultimate"
    platform = "Xbox"
    hint = "the DOA2U game folder, or its DOA1/data folder (kas00.xpr, KS_DAT.BIN, ...)"

    @classmethod
    def find_root(cls, folder):
        for f in (folder, os.path.join(folder, "data"), os.path.join(folder, "DOA1", "data"),
                  os.path.join(os.path.dirname(folder), "DOA1", "data")):
            if os.path.isdir(f) and os.path.exists(os.path.join(f, "kas00.xpr")) and os.path.exists(os.path.join(f, "KS_DAT.BIN")):
                return f
        return None

    def __init__(self, folder, names=None, sources=None):
        super().__init__(folder, names, sources)
        self.names = dict(NAMES, **(names or {}))
        self.set_sources(self.sources)
        self.entries = {}
        for fn in sorted(os.listdir(folder)):
            p = os.path.join(folder, fn)
            if not fn.lower().endswith((".xpr", ".bin")) or not os.path.isfile(p):
                continue
            with open(p, "rb") as f:
                if f.read(4) != b"XPR0":
                    continue
            stem = fn.rsplit(".", 1)[0]
            m = COSTUME.match(fn)
            if m:
                kind, char, label = "costume", m.group(1).lower(), m.group(2)
            elif stem.lower().startswith(STAGE_HINT):
                kind, char, label = "stage", None, stem
            else:
                kind, char, label = "other", None, stem
            eid = fn.lower()
            self.entries[eid] = dict(id=eid, kind=kind, char=char, label=label, path=p, size=os.path.getsize(p))
        self._tree = None

    def set_sources(self, sources):
        super().set_sources(sources)
        self.layouts = gx_layout.LayoutFinder(sources.layout_dir("doa1u"), sources.alias_path("doa1u"))

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
                groups.append(dict(title=title, list=True, items=[dict(id=e["id"], label=e["label"], size=e["size"]) for e in es]))
            self._tree = groups
        return self._tree

    def load(self, sid):
        e = self.entries[sid]
        with open(e["path"], "rb") as f:
            raw = f.read()
        title = "%s %s" % (self.names.get(e["char"], (e["char"] or "").upper()), e["label"]) if e["char"] else e["label"]
        key = sid.rsplit(".", 1)[0]
        sc, x = xpr_mdl.to_scene(sid, raw, title)
        sc.info["archive"] = os.path.basename(e["path"])
        if e["kind"] == "costume":
            path, note = self.layouts.find(key, len(x.objs), len(x.textures))
            sc.note = note
            if path:
                gx_layout.place_parts(sc, gx_layout.parse_layout(path), len(x.objs))
            if not sc.parts:
                sc.default_parts()
                sc.note = ("no layout available - parts shown at their stored origin" if self.sources.greedxplorer
                           else "parts shown at their stored origin - " + NEED_GX)
        else:
            sc.default_parts()
            if not x.objs:
                sc.note = "texture bundle (no meshes)"
        return sc
