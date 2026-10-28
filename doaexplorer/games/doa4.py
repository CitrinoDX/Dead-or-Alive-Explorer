"""Dead or Alive 4 (Xbox 360): XPR2/TPR models (same container as DOAX2), read straight from the disc image or an
extracted folder. Characters <code><costume>.tpr (+.cat) in chrone / chrtwo / chrthree.afs; stages in stg.afs,
effects in cmn.afs, menu sprites in spr.afs, online-lobby avatar parts in avt.afs.
Some costumes are colour variants: the same .tpr stored again next to a different .cat (material tints, not applied
yet), so identical files are listed once.
Half the cast swap heads: their bodies stop at the neck (eyes and teeth only) and <code>AA / BA / ... .tpr hold face
and hair. Those bodies are shown with the AA head; the other hairstyles are hidden groups in the parts panel."""
import os, re
import numpy as np
from ..afs import Afs
from .. import vfs
from .base import Game, sort_key_label
from . import tpr

NAMES = {
    "zac": "Zack", "tin": "Tina", "jan": "Jann Lee", "ein": "Ein", "ryu": "Ryu Hayabusa", "kas": "Kasumi",
    "gen": "Gen Fu", "hel": "Helena", "leo": "Leon", "bas": "Bass", "hak": "Kokoro", "hyt": "Hayate",
    "lei": "Lei Fang", "aya": "Ayane", "boy": "Eliot", "lis": "La Mariposa", "alp": "Alpha-152", "tng": "Tengu",
    "spa": "Spartan-458", "bra": "Brad Wong", "cri": "Christie", "kor": "Hitomi", "rtm": "Cutscene extras",
    "bay": "Bayman",
}
CHR = ("chrone.afs", "chrtwo.afs", "chrthree.afs")
# archive -> sidebar section for entries that are not tied to a character
OTHER = (("stg.afs", "Stages"), ("cmn.afs", "Effects"), ("spr.afs", "Menus and sprites"), ("avt.afs", "Avatars"))
AVATAR = {"hai": "hair", "cos": "outfits", "acs": "accessories", "hum": "faces", "man": "faces", "wom": "faces",
          "fai": "faces"}
HEAD = re.compile(r"^[A-Z]{2}$")   # kasAA, leiCA ...: heads; costumes are numbered


def head_placement(body, head, ht, target=None):
    """-> (4x4 for the head file's model parts, where its root lands). Head files are stored relative to different
    body nodes per character (hips, chest or neck). Both files carry the eyes: meshes under the face that match a body
    mesh give the offset (the most common one, since left and right eyes also match each other). Hair ornaments some
    bodies share with a head hang off other roots and would give a wrong offset, so any shared mesh only counts when
    nothing under the face matches (La Mariposa BA keeps its eyes as roots). Without any match (Helena) the head file's
    low-detail head, which is stored where the head belongs, gives it.
    target: where the AA head's face landed. The other hairstyles share that face but some mix conventions per piece
    (Lei Fang CA/EA), so they take whichever candidate offset puts their face there."""
    model = lambda sc: [p for p in sc.parts if p["group"] == "Model"]
    parent = {n["idx"]: ht.nodes[n["parent"]]["idx"] for n in ht.nodes if n["parent"] < len(ht.nodes)}
    children = {}
    for o in parent.values():
        children[o] = children.get(o, 0) + 1
    # the face: a big root mesh the eyes and teeth hang from (La Mariposa EA's cat-ear mask is a bigger mesh; Lei Fang
    # EA's small hair-chain roots have children too), else the largest mesh
    size = lambda p: len(head.meshes[p["mesh"]]["pos"])
    biggest = max([size(p) for p in model(head)], default=0)
    hroot = max(model(head), key=lambda p: (p["mesh"] not in parent and children.get(p["mesh"], 0) > 0
                                            and size(p) >= biggest / 4, size(p)), default=None)

    def under_face(o):
        for _ in range(64):
            o = parent.get(o)
            if o is None:
                return False
            if o == hroot["mesh"]:
                return True
        return False

    def matches(parts):
        out = []
        for hp in parts:
            hg = head.meshes[hp["mesh"]]
            for bp in model(body):
                bg = body.meshes[bp["mesh"]]
                if len(bg["pos"]) == len(hg["pos"]) and np.abs(bg["pos"] - hg["pos"]).max() < 1e-4:
                    out.append(np.asarray(bp["m"]) @ np.linalg.inv(hp["m"]))
        return out
    face = matches([p for p in model(head) if hroot and under_face(p["mesh"])])
    shared = matches(model(head))
    found = face or shared
    low = [p for p in head.parts if p["group"] == "Low detail"]
    from_low = np.eye(4)
    if low and hroot:
        from_low[:3, 3] = np.asarray(low[0]["m"])[:3, 3] - np.asarray(hroot["m"])[:3, 3]
    lands = lambda m: (m @ hroot["m"])[:3, 3] if hroot else m[:3, 3]
    if target is not None and hroot:
        P = min(shared + [from_low, np.eye(4)], key=lambda m: np.abs(lands(m) - target).max())
    elif found:
        keys = [tuple(np.round(m[:3, 3], 3)) for m in found]
        best = max(set(keys), key=lambda k: (keys.count(k), -abs(k[0])))
        P = found[keys.index(best)]
    else:
        P = from_low
    return P, lands(P)


class DOA4(Game):
    key = "doa4"
    title = "Dead or Alive 4"
    platform = "Xbox 360"
    hint = "the disc image (.iso) or an extracted folder with chrone.afs, chrtwo.afs, chrthree.afs ..."

    @classmethod
    def find_root(cls, folder):
        try:
            if vfs.is_disc_image(folder):
                src = vfs.XIso(folder)
            elif os.path.isdir(folder):
                src = vfs.DirFS(folder)
            else:
                return None
            return folder if all(src.exists(a) for a in CHR) else None
        except (OSError, ValueError):
            return None

    def __init__(self, folder, names=None, sources=None):
        super().__init__(folder, names, sources)
        self.names = dict(NAMES, **(names or {}))
        self.src = vfs.open_source(folder)
        self.afs = {a: Afs(a, self.src.open(a)) for a in CHR + tuple(a for a, _ in OTHER) if self.src.exists(a)}
        self.entries = {}
        sections = dict(OTHER)
        for arch, afs in self.afs.items():
            first = {}    # (stored name, size) -> entry: colour variants repeat the same .tpr under the same name
            for i, nm in enumerate(afs.names):
                if afs.size(i) < 64 or afs.read(i, 4) != b"XPR2":
                    continue
                nm = nm or "%s_%04d" % (arch[:-4], i)
                stem = nm.rsplit(".", 1)[0] if "." in nm else nm
                if arch in CHR:
                    # a costume's own name is on its .cat: the .tpr copies of colour variants keep the first one's name
                    cat = afs.names[i + 1] if i + 1 < len(afs) else None
                    if cat and cat.lower().endswith(".cat") and cat[:3].lower() == stem[:3].lower():
                        stem = cat[:-4]
                    same = (nm.lower(), afs.size(i))
                    if same in first:
                        if stem[3:] != first[same]["label"] and stem[3:] not in first[same]["variants"]:
                            first[same]["variants"].append(stem[3:])
                        continue
                    e = dict(archive=arch, index=i, char=stem[:3].lower(), section="Characters", label=stem[3:],
                             name=nm, size=afs.size(i), variants=[])
                    first[same] = e
                else:
                    section = sections[arch]
                    if arch == "avt.afs":
                        section = "Avatar " + AVATAR.get(stem[:3].lower(), "pets and other")
                    e = dict(archive=arch, index=i, char=None, section=section, label=stem, name=nm,
                             size=afs.size(i), variants=[])
                self.entries["%s:%d" % (arch[:-4], i)] = e
        self.heads = {}   # character -> head entry ids, AA first
        for eid, e in self.entries.items():
            e["head"] = bool(e["char"]) and bool(HEAD.match(e["label"]))
            if e["head"]:
                self.heads.setdefault(e["char"], []).append(eid)
        for ids in self.heads.values():
            ids.sort(key=lambda eid: self.entries[eid]["label"])
        self._tree = None

    def tree(self):
        if self._tree is None:
            by = {}
            for eid, e in self.entries.items():
                by.setdefault(("char", e["char"]) if e["char"] else ("sec", e["section"]), []).append((eid, e))
            order = [s for _, s in OTHER]

            def group_key(k):
                kind, name = k
                if kind == "char":
                    return (0, self.names.get(name, name).lower(), name)
                return (1, order.index(name) if name in order else len(order), name)
            groups = []
            for k in sorted(by, key=group_key):
                kind, name = k
                items = []
                for eid, e in sorted(by[k], key=lambda x: sort_key_label(x[1]["label"])):
                    lab = e["label"] + ("  (head)" if e["head"] else "")
                    if e["variants"]:
                        lab += "  (+%d colour variant%s)" % (len(e["variants"]), "s" if len(e["variants"]) > 1 else "")
                    items.append(dict(id=eid, label=lab, size=e["size"]))
                title = "%s (%s)" % (self.names.get(name, name), name) if kind == "char" else name
                groups.append(dict(title=title, list=True, items=items))
            self._tree = groups
        return self._tree

    def load(self, sid):
        e = self.entries[sid]
        raw = self.afs[e["archive"]].read(e["index"])
        who = self.names.get(e["char"], e["char"]) if e["char"] else e["section"]
        sc, t = tpr.to_scene(sid, raw, "%s - %s" % (who, e["label"]), character=bool(e["char"]))
        sc.info["archive"] = "%s #%d (%s)" % (e["archive"], e["index"], e["name"])
        notes = []
        heads = [] if e["head"] or not e["char"] else self.heads.get(e["char"], [])
        face = None   # where the AA head's face landed
        for k, hid in enumerate(heads):
            h = self.entries[hid]
            hs, ht = tpr.to_scene(hid, self.afs[h["archive"]].read(h["index"]), character=True)
            P, root = head_placement(sc, hs, ht, face)
            if face is None:
                face = root

            def place(p, lab=h["label"], first=(k == 0), P=P, root=root):
                if p["group"] == "Model":
                    return "Head " + lab, first, P @ p["m"]
                # the head file's low-detail and shadow heads sit at their own root: move them where the head went
                m = np.array(p["m"], float)
                m[:3, 3] = root
                return p["group"], False, m
            sc.merge(hs, h["label"] + " ", place)
        if e["section"] == "Stages":
            # sky domes and far backdrops (thousands of units out) carry no texture and would only show as grey
            plain = [p for p in sc.parts if all(s["tex"] < 0 for s in sc.meshes[p["mesh"]]["subs"])]
            if len(plain) < len(sc.parts):
                for p in plain:
                    p["group"], p["visible"] = "Untextured (sky, backdrops)", False
        if heads:
            labels = [self.entries[h]["label"] for h in heads]
            notes.append("head %s attached" % labels[0] + ("; other hairstyles %s are in the parts panel"
                                                           % ", ".join(labels[1:]) if len(labels) > 1 else ""))
        if not t.objs:
            notes.append("texture bundle (no meshes)")
        elif not t.nodes:
            notes.append("no node hierarchy - parts shown at their stored origin")
        if e["variants"]:
            notes.append("colour variants %s use this same model with their own .cat tints (not applied)"
                         % ", ".join(e["variants"]))
        sc.note = "; ".join(notes)
        return sc
