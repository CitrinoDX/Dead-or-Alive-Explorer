"""The common model description every game module produces and the viewer/exporters consume.

meshes[i]  = dict(pos (N,3) f4, nrm (N,3) f4, uv (N,2) f4, idx (M,) u4 triangle list,
                  subs=[dict(start, count, tex, transparent, cull, diffuse, env?)])  or None
             env: tex is a reflection map, looked up from the view-space normal instead of the UVs
parts[j]   = dict(name, group, mesh, m (4x4 column-vector matrix), visible)
textures[k]= dict(w, h, fmt, name) + a decoder returning (h,w,4) uint8 RGBA
basis      = orientation applied on top of every part (viewer and export alike)
"""
import base64, math
import numpy as np
from . import texture

# 180 degrees about Y: matches GreedXplorer's view of the Xbox data (do not undo).
# Front faces are counter-clockwise: the winding agrees with the stored vertex normals on 99.5-100% of triangles
# in DOA2U, DOAX and DOAX2 (the earlier "cw" hid the outside of single-sided materials and flipped lighting).
XBOX_BASIS = dict(m=[-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1], front="ccw")

CULL_NONE, CULL_BACK, CULL_FRONT = 0, 1, 2


def euler_matrix(r):
    """r = (rx, ry, rz) degrees -> 3x3, R = Rz * Ry * Rx"""
    rx, ry, rz = [math.radians(v) for v in r]
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    X = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Z @ Y @ X


def trs(t=(0, 0, 0), r=(0, 0, 0)):
    m = np.eye(4)
    m[:3, :3] = euler_matrix(r)
    m[:3, 3] = t
    return m


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode("ascii")


class Scene:
    def __init__(self, sid, title=None):
        self.id = sid
        self.title = title or sid
        self.meshes = []
        self.parts = []
        self.textures = []
        self.note = ""
        self.basis = XBOX_BASIS
        self.info = {}
        self._decoders = []
        self._png = {}
        self._alpha = {}

    # ---- building
    def add_texture(self, w, h, fmt, decode, name=None):
        self.textures.append(dict(w=int(w), h=int(h), fmt=fmt, name=name or "tex%03d" % len(self.textures)))
        self._decoders.append(decode)
        return len(self.textures) - 1

    def add_part(self, name, mesh, m=None, group="All", visible=True):
        self.parts.append(dict(name=name, group=group, mesh=mesh, m=np.eye(4) if m is None else np.asarray(m, float),
                               visible=visible))

    def merge(self, other, prefix, place):
        """Append another scene's textures, meshes and parts (names prefixed). place(part) -> (group, visible, matrix)."""
        toff, moff = len(self.textures), len(self.meshes)
        for k, t in enumerate(other.textures):
            self.add_texture(t["w"], t["h"], t["fmt"], other._decoders[k], name=prefix + t["name"])
        for g in other.meshes:
            if g is not None:
                g = dict(g, subs=[dict(s, tex=s["tex"] + toff if s["tex"] >= 0 else s["tex"]) for s in g["subs"]])
            self.meshes.append(g)
        for p in other.parts:
            group, visible, m = place(p)
            self.add_part(prefix + p["name"], moff + p["mesh"], m, group, visible)

    def default_parts(self, group="All"):
        """One part per non-empty mesh at its stored origin."""
        for i, g in enumerate(self.meshes):
            if g is not None:
                self.add_part((g.get("name") or "mesh_%d" % i), i, group=group)

    # ---- textures
    def texture_rgba(self, i):
        t = self.textures[i]
        try:
            img = self._decoders[i]()
        except Exception as e:  # a broken texture should never take the model down
            print("texture %s #%d: %s: %s" % (self.id, i, type(e).__name__, e))
            img = None
        return img if img is not None else texture.placeholder(t["w"], t["h"])

    def texture_png(self, i, opaque=False):
        """opaque=True drops the alpha channel (normal/specular maps often keep alpha at zero)"""
        k = (i, opaque)
        if k not in self._png:
            img = self.texture_rgba(i)
            if not opaque:
                self._alpha.setdefault(i, texture.alpha_class(img))
            if opaque:
                img = img.copy()
                img[:, :, 3] = 255
            self._png[k] = texture.png_bytes(img)
        return self._png[k]

    def texture_alpha(self, i):
        if i not in self._alpha:
            self.texture_png(i)   # decodes once and caches the PNG the viewer is about to ask for anyway
        return self._alpha[i]

    def sub_blend(self, s):
        """How a material is drawn: 'opaque', 'mask' (alpha-tested) or 'blend'. Materials flagged transparent often use
        fully opaque textures (Ayane's bow); blending those without depth writes shows their inside, so they draw solid."""
        if not s.get("transparent"):
            return "opaque"
        if not 0 <= s["tex"] < len(self.textures):
            return "opaque"
        return self.texture_alpha(s["tex"])

    # ---- output
    def payload(self):
        meshes = []
        for g in self.meshes:
            if g is None:
                meshes.append(None)
                continue
            subs = [dict(s, blend=self.sub_blend(s)) for s in g["subs"]]
            meshes.append(dict(name=g.get("name"), pos=b64(g["pos"].astype("<f4")), nrm=b64(g["nrm"].astype("<f4")),
                               uv=b64(g["uv"].astype("<f4")), idx=b64(g["idx"].astype("<u4")), subs=subs,
                               verts=int(len(g["pos"])), tris=int(len(g["idx"]) // 3)))
        parts = [dict(name=p["name"], group=p["group"], mesh=p["mesh"], visible=p["visible"],
                      m=[float(v) for v in np.asarray(p["m"]).T.reshape(-1)]) for p in self.parts]
        return dict(id=self.id, title=self.title, meshes=meshes, parts=parts, note=self.note, basis=self.basis,
                    textures=[dict(i=i, **t) for i, t in enumerate(self.textures)], info=self.info)


def merge_geometry(chunks):
    """chunks: list of dict(pos, nrm|None, uv|None, tris (n,3), sub=dict(...)) sharing nothing -> one mesh dict.
    Vertices are not shared between chunks, so each chunk keeps its own vertex range."""
    pos, nrm, uv, idx, subs = [], [], [], [], []
    nv = ni = 0
    for c in chunks:
        p = np.asarray(c["pos"], np.float32)
        if not len(p) or not len(c["tris"]):
            continue
        pos.append(p)
        nrm.append(np.asarray(c["nrm"], np.float32) if c.get("nrm") is not None else np.zeros_like(p))
        uv.append(np.asarray(c["uv"], np.float32) if c.get("uv") is not None else np.zeros((len(p), 2), np.float32))
        t = np.asarray(c["tris"], np.int64).reshape(-1) + nv
        idx.append(t)
        subs.append(dict(c["sub"], start=ni, count=int(len(t))))
        nv += len(p)
        ni += len(t)
    if not pos:
        return None
    return dict(pos=np.concatenate(pos), nrm=np.concatenate(nrm), uv=np.concatenate(uv),
                idx=np.concatenate(idx).astype(np.uint32), subs=subs)


def orient_to_normals(pos, nrm, tris):
    """Flip triangles whose winding (counter-clockwise = front) disagrees with their stored vertex normals."""
    if nrm is None or not len(tris):
        return tris
    p = np.asarray(pos, np.float64)
    ng = np.cross(p[tris[:, 1]] - p[tris[:, 0]], p[tris[:, 2]] - p[tris[:, 0]])
    flip = np.einsum("ij,ij->i", ng, np.asarray(nrm, np.float64)[tris].sum(1)) < 0
    out = tris.copy()
    out[flip] = out[flip][:, [0, 2, 1]]
    return out


def strip_to_tris(seg, restart=None):
    """Triangle strip -> (n,3) triangles with D3D winding; parity restarts after each restart index.
    Degenerate triangles are dropped (they still advance the parity)."""
    seg = np.asarray(seg, np.int64)
    if len(seg) < 3:
        return np.zeros((0, 3), np.int64)
    n = len(seg)
    pos = np.arange(n)
    if restart is not None:
        is_r = seg == restart
        last = np.maximum.accumulate(np.where(is_r, pos, -1))
        local = pos - last - 1
    else:
        is_r = np.zeros(n, bool)
        local = pos
    a, b, c = seg[:-2], seg[1:-1], seg[2:]
    flip = (local[:-2] & 1) == 1
    t = np.stack([a, np.where(flip, c, b), np.where(flip, b, c)], axis=1)
    keep = ~(is_r[:-2] | is_r[1:-1] | is_r[2:])
    keep &= (t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])
    return t[keep]
