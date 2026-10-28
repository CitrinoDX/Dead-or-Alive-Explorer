"""Dead or Alive Xtreme 2 (Xbox 360): XPR2/TPR models in chr / werone / wertwo / itm / boat / stg / avt .afs, read
straight from the disc image or an extracted folder."""
import os
from ..afs import Afs
from .. import vfs
from .base import Game
from . import tpr

NAMES = {
    "vks": "Kasumi", "vay": "Ayane", "vht": "Hitomi", "vhe": "Helena", "vcr": "Christie", "vco": "Kokoro",
    "vle": "Lei Fang", "vls": "Lisa", "vtn": "Tina",
}
# archive -> sidebar section for entries that are not tied to a character
ARCHIVES = (("chr", "Bodies"), ("werone", "Swimsuits"), ("wertwo", "Swimsuits"), ("itm", "Items"),
            ("boat", "Boats"), ("stg", "Stages"), ("avt", "Avatar"))


class DOAX2(Game):
    key = "doax2"
    title = "Dead or Alive Xtreme 2"
    platform = "Xbox 360"
    hint = "the disc image (.iso) or an extracted folder with chr.afs, werone.afs, ... and default.xex"

    @classmethod
    def find_root(cls, folder):
        try:
            if vfs.is_disc_image(folder):
                cands = [(folder, vfs.XIso(folder))]
            elif os.path.isdir(folder):
                cands = [(f, vfs.DirFS(f)) for f in (folder, os.path.join(folder, "doax2")) if os.path.isdir(f)]
            else:
                return None
            for f, src in cands:
                if src.exists("chr.afs") and src.exists("default.xex"):
                    return f
            return None
        except (OSError, ValueError):
            return None

    def __init__(self, folder, names=None, sources=None):
        super().__init__(folder, names, sources)
        self.names = dict(NAMES, **(names or {}))
        self.src = vfs.open_source(folder)
        self.afs = {a: Afs(a + ".afs", self.src.open(a + ".afs")) for a, _ in ARCHIVES if self.src.exists(a + ".afs")}
        self.entries = {}
        for arch, section in ARCHIVES:
            afs = self.afs.get(arch)
            if not afs:
                continue
            for i, nm in enumerate(afs.names):
                if afs.size(i) < 64 or afs.read(i, 4) != b"XPR2":
                    continue
                nm = nm or "%s_%04d" % (arch, i)
                stem = nm.rsplit(".", 1)[0] if "." in nm else nm
                code = stem[:3].lower()
                char = code if code in self.names and arch in ("chr", "werone", "wertwo") else None
                label = stem[4:] if char and stem[3:4] == "_" else stem
                if arch == "chr" and char:
                    label = "body " + stem[3:]
                self.entries["%s:%d" % (arch, i)] = dict(archive=arch, index=i, char=char, section=section,
                                                         label=label, name=nm, size=afs.size(i))
        self._tree = None

    def tree(self):
        if self._tree is None:
            groups, by = [], {}
            for eid, e in self.entries.items():
                key = ("char", e["char"]) if e["char"] else ("sec", e["section"])
                by.setdefault(key, []).append((eid, e))
            for (kind, k), es in sorted(by.items(), key=lambda kv: (kv[0][0] != "char", self.names.get(kv[0][1], kv[0][1]))):
                title = "%s (%s)" % (self.names[k], k) if kind == "char" else k
                seen = {}
                for _, e in es:
                    seen[e["label"]] = seen.get(e["label"], 0) + 1
                items = []
                for eid, e in sorted(es, key=lambda x: (x[1]["archive"] != "chr", x[1]["archive"], x[1]["label"].lower(), x[1]["index"])):
                    lab = e["label"] if seen[e["label"]] == 1 else "%s  #%d" % (e["label"], e["index"])
                    if kind == "char" and e["archive"] != "chr":
                        lab = "%s  (%s)" % (lab, e["archive"])
                    items.append(dict(id=eid, label=lab, size=e["size"]))
                groups.append(dict(title=title, list=True, items=items))
            self._tree = groups
        return self._tree

    def load(self, sid):
        e = self.entries[sid]
        raw = self.afs[e["archive"]].read(e["index"])
        who = self.names.get(e["char"], "") if e["char"] else e["section"]
        sc, t = tpr.to_scene(sid, raw, "%s - %s" % (who, e["label"]))
        sc.info["archive"] = "%s.afs #%d (%s)" % (e["archive"], e["index"], e["name"])
        if not t.objs:
            sc.note = "texture bundle (no meshes)"
        elif not t.nodes:
            sc.note = "no node hierarchy - parts shown at their stored origin"
        return sc
