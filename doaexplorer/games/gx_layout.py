"""GreedXplorer per-costume XML layouts: where each limb mesh sits (tx/ty/tz, mirrored limbs at -tx).
Limbs are stored around their own pivots, so without a layout they all pile up at the origin."""
import os, re, xml.etree.ElementTree as ET
from ..scene import trs


def load_alias(path):
    """alias.txt: [char] section, costume=objnum*1000+texnum"""
    sig = {}
    if not path or not os.path.exists(path):
        return sig
    sec = None
    for line in open(path, encoding="latin-1"):
        line = line.strip()
        if line.startswith("["):
            sec = line[1:-1]
        elif "=" in line and sec:
            k, v = line.split("=", 1)
            if v.strip().isdigit():
                sig.setdefault(k.strip().lower(), int(v))
    return sig


def parse_layout(path):
    root = ET.parse(path).getroot()
    groups = []
    for g in root.iter("MeshGroup"):
        elems = []
        for e in g.findall("Elem"):
            def num(k):
                try:
                    return float(e.get(k, 0) or 0)
                except ValueError:
                    return 0.0

            def objid(s):
                m = re.match(r"OBJ_(\d+)$", s or "")
                return int(m.group(1)) if m else None
            elems.append(dict(name=e.get("Name", ""), mesh=objid(e.get("Mesh")), mirror=objid(e.get("MirrorMesh")),
                              t=(num("tx"), num("ty"), num("tz")), r=(num("rx"), num("ry"), num("rz"))))
        groups.append((g.get("Name", "Group"), elems))
    return groups


def parse_maxscript(path):
    """3ds Max layout script for one DOA2U costume (made for the DOAU Exporter's .3ds files): an importFile per mesh, then
    '$meshNN.pos = [x, y, z]' in centimetres, mesh NN being OBJ_NN, translation only -> {mesh: (x, y, z) in metres}"""
    out = {}
    for line in open(path, encoding="latin-1"):
        m = re.match(r"\s*\$mesh(\d+)\.pos\s*=\s*\[([^\]]*)\]", line)
        if m:
            try:
                out[int(m.group(1))] = tuple(float(v) / 100 for v in m.group(2).split(","))
            except ValueError:
                pass
    return out


class LayoutFinder:
    def __init__(self, xml_dir, alias_path=None):
        self.xml_dir = xml_dir
        self.alias = load_alias(alias_path)
        self.files = {}
        self._maxobj = {}
        if xml_dir and os.path.isdir(xml_dir):
            for f in os.listdir(xml_dir):
                if f.lower().endswith(".xml"):
                    self.files[f[:-4].lower()] = os.path.join(xml_dir, f)

    def max_obj(self, key):
        """highest OBJ_n a layout references (its minimum mesh count is this + 1)"""
        if key not in self._maxobj:
            ids = [e[k] for _, es in parse_layout(self.files[key]) for e in es for k in ("mesh", "mirror") if e[k] is not None]
            self._maxobj[key] = max(ids) if ids else -1
        return self._maxobj[key]

    def find(self, eid, nobjs, ntex):
        """returns (path|None, note): exact XML -> same-character alias signature -> same-character layout
        that references exactly the meshes this file has -> none"""
        if eid in self.files:
            return self.files[eid], "exact layout %s.xml" % eid
        char = eid[:3]
        want = nobjs * 1000 + ntex
        same = sorted(k for k in self.files if k.startswith(char))
        for k in same:
            if self.alias.get(k) == want:
                return self.files[k], "approximate layout (same mesh/texture count as %s)" % k
        for k in same:
            if self.alias.get(k, -1) // 1000 == nobjs:
                return self.files[k], "approximate layout (same mesh count as %s)" % k
        fits = [k for k in same if self.max_obj(k) == nobjs - 1]
        if fits:
            return self.files[fits[0]], "approximate layout borrowed from %s (same character and mesh count)" % fits[0]
        return None, "no layout available"


def place_parts(scene, groups, nobjs):
    for gname, elems in groups:
        for e in elems:
            vis = gname == "Character" or (gname == "Misc" and not re.match(r"OBJ_\d+$", e["name"]))
            if e["mesh"] is not None and e["mesh"] < nobjs:
                scene.add_part(e["name"], e["mesh"], trs(e["t"], e["r"]), gname, vis)
            if e["mirror"] is not None and e["mirror"] < nobjs:
                # the mirror mesh is the X-mirror image of the original, so its rotation is mirrored too:
                # S R S with S = diag(-1, 1, 1)  ->  (rx, -ry, -rz)
                t = (-e["t"][0], e["t"][1], e["t"][2])
                r = (e["r"][0], -e["r"][1], -e["r"][2])
                scene.add_part(e["name"] + " (mirror)", e["mirror"], trs(t, r), gname, vis)
