"""Team Ninja TPR / TP models in Xbox 360 XPR2 containers (DOAX2, DOA4). Big-endian.
Layout follows the 'TPR-GMD' Blender importer (xentax, 2013):
  XPR2 header: magic, header size, data size, resource count; 16-byte entries (type, offset, size, name offset)
  USER resources: header numbers, 'MdlGeo' (objects/materials/vertex decls), 'MdlInfo', 'Hie' (node matrices)
  TX2D/VBUF/IBUF resources point into the data block that follows the header."""
import struct
import numpy as np
from .. import texture
from ..scene import Scene, merge_geometry, strip_to_tris, CULL_NONE

# D3DDECLTYPE (Xbox 360) -> (numpy dtype, components, decoder)
FLOAT2, FLOAT3, FLOAT4 = 0x2C23A5, 0x2A23B9, 0x1A23A6
D3DCOLOR, UBYTE4, UBYTE4N = 0x182886, 0x1A2286, 0x1A2086
FLOAT16_2, FLOAT16_4 = 0x2C235F, 0x1A2360
DEC4N, HEND3N = 0x1A2187, 0x2A2190
USAGE_POS, USAGE_WEIGHT, USAGE_INDEX, USAGE_NORMAL, USAGE_UV, USAGE_TANGENT, USAGE_COLOR = 0, 1, 2, 3, 5, 6, 10


class Tpr:
    def __init__(self):
        self.data = b""
        self.objs = []       # dict(index, decls, materials)
        self.textures = []   # dict(name, fmt, endian, w, h, offset, tiled, kind)
        self.nodes = []      # dict(idx, parent, m (4x4 local, column-vector))


def _signed_bits(v, shift, bits):
    x = (v >> shift) & ((1 << bits) - 1)
    return np.where(x & (1 << (bits - 1)), x.astype(np.int64) - (1 << bits), x).astype(np.float32)


def decode_attr(raw, off, dtype):
    """raw: (N, stride) uint8 vertex rows -> (N, k) float32, or None for unknown types"""
    n = raw.shape[0]
    col = lambda nb: np.ascontiguousarray(raw[:, off:off + nb])
    if dtype in (FLOAT2, FLOAT3, FLOAT4):
        k = {FLOAT2: 2, FLOAT3: 3, FLOAT4: 4}[dtype]
        return col(4 * k).view(">f4").reshape(n, k).astype(np.float32)
    if dtype in (FLOAT16_2, FLOAT16_4):
        k = 2 if dtype == FLOAT16_2 else 4
        return col(2 * k).view(">f2").reshape(n, k).astype(np.float32)
    if dtype in (UBYTE4N, D3DCOLOR):
        return col(4).astype(np.float32) / 255.0
    if dtype == UBYTE4:
        return col(4).astype(np.float32)
    if dtype == DEC4N:   # 10:10:10:2 signed normalised, x in the low bits
        v = col(4).view(">u4").reshape(n).astype(np.int64)
        return np.stack([_signed_bits(v, 0, 10) / 511, _signed_bits(v, 10, 10) / 511, _signed_bits(v, 20, 10) / 511,
                         _signed_bits(v, 30, 2)], 1)
    if dtype == HEND3N:  # 11:11:10 signed normalised
        v = col(4).view(">u4").reshape(n).astype(np.int64)
        return np.stack([_signed_bits(v, 0, 11) / 1023, _signed_bits(v, 11, 11) / 1023, _signed_bits(v, 22, 10) / 511], 1)
    return None


def _table(d, base):
    """generic Team Ninja chunk: count at +0x14, offset table (relative to the chunk) at +0x20"""
    n, toff = struct.unpack_from(">I", d, base + 0x14)[0], struct.unpack_from(">I", d, base + 0x20)[0]
    return [base + o for o in struct.unpack_from(">%dI" % n, d, base + toff)] if n else []


def parse_tpr(d):
    if d[:3] == b"GMD":
        d = d[0x1000:]
    magic, hsize, dsize, count = struct.unpack_from(">4s3I", d, 0)
    if magic != b"XPR2":
        raise ValueError("not an XPR2 container")
    base = 0xC
    data0 = base + hsize
    t = Tpr()
    t.data = d
    users, vbufs, ibufs, texents = {}, [], [], []
    for k in range(count):
        typ, off, sz, nm = struct.unpack_from(">4s3I", d, 0x10 + 16 * k)
        off += base
        name = d[base + nm:base + nm + 64].split(b"\0")[0].decode("latin-1") if nm else ""
        if typ == b"USER":
            tag = d[off:off + 8].split(b"\0")[0].decode("latin-1", "replace")
            users.setdefault(tag if tag in ("MdlGeo", "MdlInfo", "Hie") else "hdr%d" % k, off)
        elif typ == b"VBUF":
            vbufs.append(data0 + (struct.unpack_from(">I", d, off + sz - 8)[0] & ~0xF))
        elif typ == b"IBUF":
            ibufs.append(data0 + (struct.unpack_from(">I", d, off + sz - 8)[0] & ~0xF))
        elif typ in (b"TX2D", b"TX3D", b"TXCM"):
            texents.append((typ, off, sz, name))
    for i, (typ, off, sz, name) in enumerate(texents):
        # the 6-dword GPU fetch constant ends the header (0x34 bytes in DOAX2, 0x28 in DOA4)
        fd0, fd1, fd2 = struct.unpack_from(">3I", d, off + sz - 0x18)
        if typ == b"TX3D":
            w, h = 1 + (fd2 & 0x7FF), 1 + ((fd2 >> 11) & 0x7FF)
        else:
            w, h = 1 + (fd2 & 0x1FFF), 1 + ((fd2 >> 13) & 0x1FFF)
        t.textures.append(dict(name=name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or "tex%03d" % i, kind=typ.decode(),
                               fmt=fd1 & 0x3F, endian=(fd1 >> 6) & 3, offset=data0 + (fd1 & 0xFFFFF000),
                               w=w, h=h, tiled=bool(fd0 & 0x80000000)))
    if "Hie" in users:
        for nb in _table(d, users["Hie"]):
            m = np.array(struct.unpack_from(">16f", d, nb), np.float64).reshape(4, 4).T  # stored row-vector style
            idx, parent, nch = struct.unpack_from(">3H", d, nb + 64)
            t.nodes.append(dict(idx=idx, parent=parent, m=m))
    if "MdlGeo" in users:
        for oi, ob in enumerate(_table(d, users["MdlGeo"])):
            t.objs.append(_parse_obj(d, ob, oi, vbufs, ibufs))
    return t


def _parse_obj(d, ob, oi, vbufs, ibufs):
    u = lambda o: struct.unpack_from(">I", d, o)[0]
    obj = dict(index=oi, decls=[], materials=[])
    declrel = u(ob + 0x28)
    if declrel:
        for sd in _table(d, ob + declrel):
            size, morph, ibi, nidx, nlayers, nverts, _ = struct.unpack_from(">7I", d, sd)
            layers = [struct.unpack_from(">2IH2B", d, sd + 0x30 + 0xC * i) for i in range(max(0, nlayers - 1))]
            vbi, stride = struct.unpack_from(">2I", d, sd + size)
            obj["decls"].append(dict(ibuf=ibi, nidx=nidx, nverts=nverts, vbuf=vbi, stride=stride, layers=layers))
    for mb in _table(d, ob):
        mi, transp, decl, _, istart, icount, ntex, toff = struct.unpack_from(">8I", d, mb)
        cols = [struct.unpack_from(">4f", d, mb + 0x80 + 16 * i) for i in range(4)]   # ambient, diffuse, specular, emissive
        texs = [struct.unpack_from(">3I", d, mb + toff + 0x40 * k) for k in range(min(ntex, 16))]  # uv set, map type, texture
        obj["materials"].append(dict(index=mi, transparent=bool(transp), decl=decl, istart=istart, icount=icount,
                                     colors=cols, textures=texs))
    obj["vbufs"], obj["ibufs"] = vbufs, ibufs
    return obj


def obj_geometry(t, obj, ntex):
    d = t.data
    verts = []
    for dc in obj["decls"]:
        if dc["vbuf"] >= len(obj["vbufs"]) or dc["ibuf"] >= len(obj["ibufs"]):
            verts.append(None)
            continue
        vb = obj["vbufs"][dc["vbuf"]]
        raw = np.frombuffer(d, np.uint8, count=dc["nverts"] * dc["stride"], offset=vb).reshape(dc["nverts"], dc["stride"])
        pos = nrm = uv = None
        for off, dtype, usage, layer, _ in dc["layers"]:
            if usage == USAGE_POS and layer == 0 and pos is None:
                pos = decode_attr(raw, off, dtype)
            elif usage == USAGE_NORMAL and nrm is None:
                a = decode_attr(raw, off, dtype)
                if a is not None and a.shape[1] >= 3:
                    nrm = a[:, :3]
            elif usage == USAGE_UV and layer == 0 and uv is None:
                a = decode_attr(raw, off, dtype)
                if a is not None:
                    uv = a[:, :2]
        ind = np.frombuffer(d, ">u2", count=dc["nidx"], offset=obj["ibufs"][dc["ibuf"]]).astype(np.int64)
        verts.append(None if pos is None else (pos[:, :3], nrm, uv, ind))
    chunks = []
    for mt in obj["materials"]:
        if mt["decl"] >= len(verts) or verts[mt["decl"]] is None:
            continue
        pos, nrm, uv, ind = verts[mt["decl"]]
        tris = strip_to_tris(ind[mt["istart"]:mt["istart"] + mt["icount"]], restart=0xFFFF)
        if not len(tris) or tris.max() >= len(pos):
            continue
        used, inv = np.unique(tris, return_inverse=True)
        tex = -1
        for slot, maptype, gi in mt["textures"]:        # diffuse: first colour map on UV set 0
            if gi < ntex and slot == 0 and maptype in (0, 1):
                tex = gi
                break
        chunks.append(dict(pos=pos[used], nrm=None if nrm is None else nrm[used], uv=None if uv is None else uv[used],
                           tris=inv.reshape(-1, 3),
                           sub=dict(tex=int(tex), transparent=mt["transparent"], cull=CULL_NONE,
                                    diffuse=[1.0, 1.0, 1.0, 1.0])))
    g = merge_geometry(chunks)
    if g is not None:
        g["name"] = "OBJ%02d" % obj["index"]
    return g


def global_matrices(t):
    """object index -> 4x4 global matrix from the Hie node tree"""
    glob = [None] * len(t.nodes)

    def get(i, depth=0):
        if glob[i] is None:
            n = t.nodes[i]
            p = n["parent"]
            glob[i] = n["m"] if p == 0xFFFF or p >= len(t.nodes) or depth > 64 else get(p, depth + 1) @ n["m"]
        return glob[i]
    out = {}
    for i, n in enumerate(t.nodes):
        out.setdefault(n["idx"], get(i))
    return out


def detail_groups(t, meshes, mats, tol=0.01):
    """object index -> 'Model' / 'Low detail' / 'Shadow' / 'Extras'. DOA4 files carry the whole model again at low
    detail plus an untextured shadow copy made from it. Shadow objects pair with the textured object that has the same
    bounds and the closest vertex count; a hierarchy root whose objects are mostly such partners is the low-detail set.
    Extras: single quads (shadow / reflection planes) and, in body files, props reaching well past the body (Zack's
    rope runs 500 units out). Files without a shadow copy come back as a single 'All' group."""
    nt = len(t.textures)
    live = [o for o, g in enumerate(meshes) if g is not None]
    shadow = {o for o in live if not any(gi < nt for m in t.objs[o]["materials"] for _, _, gi in m["textures"])}
    if not shadow:
        return {o: "All" for o in live}
    box = {o: (meshes[o]["pos"].min(0), meshes[o]["pos"].max(0)) for o in live}
    partner = set()
    for so in shadow:
        lo, hi = box[so]
        same = [o for o in live if o not in shadow and np.abs(box[o][0] - lo).max() < tol and np.abs(box[o][1] - hi).max() < tol]
        if same:
            ns = len(meshes[so]["pos"])
            partner.add(min(same, key=lambda o: abs(np.log(len(meshes[o]["pos"]) / ns))))
    node_of = {n["idx"]: i for i, n in enumerate(t.nodes)}

    def root(o):
        i = node_of.get(o)
        if i is None:
            return ("obj", o)
        for _ in range(128):
            p = t.nodes[i]["parent"]
            if p == 0xFFFF or p >= len(t.nodes):
                break
            i = p
        return t.nodes[i]["idx"]
    by_root = {}
    for o in live:
        by_root.setdefault(root(o), []).append(o)
    out = {}
    for objs in by_root.values():
        tex = [o for o in objs if o not in shadow]
        hits = sum(o in partner for o in tex)
        low = tex and hits >= (0.5 * len(tex) if len(tex) >= 3 else len(tex))
        for o in objs:
            out[o] = "Shadow" if o in shadow else "Low detail" if low else "Model"

    def world_box(o):
        m = np.asarray(mats.get(o, np.eye(4)))
        p = meshes[o]["pos"] @ m[:3, :3].T + m[:3, 3]
        return p.min(0), p.max(0)
    low = [o for o in live if out[o] == "Low detail"]
    body_lo = body_hi = None
    if len(low) >= 8:   # a whole low-detail body, not just a low-detail head
        boxes = [world_box(o) for o in low]
        body_lo, body_hi = np.min([b[0] for b in boxes], 0) - 0.5, np.max([b[1] for b in boxes], 0) + 0.5
    for o in live:
        if out[o] != "Model":
            continue
        if len(meshes[o]["pos"]) <= 4:
            out[o] = "Extras"
        elif body_lo is not None:
            lo, hi = world_box(o)
            if (lo < body_lo).any() or (hi > body_hi).any():
                out[o] = "Extras"
    return out


def to_scene(sid, raw, title=None, character=False):
    """character: sort a DOA4 character file into model / low detail / shadow / extras (see detail_groups)"""
    t = parse_tpr(raw)
    sc = Scene(sid, title)
    sc.meshes = [obj_geometry(t, ob, len(t.textures)) for ob in t.objs]
    mats = global_matrices(t)
    if character:
        groups = detail_groups(t, sc.meshes, mats)
    else:
        groups = {i: "All" for i, g in enumerate(sc.meshes) if g is not None}
    for i, g in enumerate(sc.meshes):
        if g is not None:
            sc.add_part(g["name"], i, mats.get(i), group=groups[i], visible=groups[i] in ("Model", "All"))
    for tx in t.textures:
        sc.add_texture(tx["w"], tx["h"], texture.x360_format_name(tx["fmt"]) + ("" if tx["kind"] == "TX2D" else " " + tx["kind"]),
                       (lambda tx=tx: texture.decode_x360(t.data, tx["offset"], tx["fmt"], tx["endian"], tx["w"], tx["h"], tx["tiled"])),
                       name=tx["name"])
    sc.info = dict(meshes=len(t.objs), textures=len(t.textures), nodes=len(t.nodes), format="XPR2 / TPR (Xbox 360)")
    return sc, t
