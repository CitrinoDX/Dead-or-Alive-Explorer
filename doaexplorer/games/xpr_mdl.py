"""Xbox XPR0 bundles: generic resource walk (textures, vertex buffers) plus the Team Ninja 'MDL' user block
used by DOA2U (layout from the DOAU Blender exporter, verified against decrypted kas00.xpr)."""
import struct
import numpy as np
from .. import texture
from ..scene import (Scene, merge_geometry, strip_to_tris, orient_to_normals, vertex_normals,
                     CULL_NONE, CULL_BACK, CULL_FRONT)
from . import xbox_crypt


class Material:
    __slots__ = ("matid", "nrm_mode", "bound", "diffuse", "ambient", "specular", "emissive",
                 "power", "textures", "slot", "ind_start", "ind_tris", "transparent", "strips", "tex_field")


class Obj:
    __slots__ = ("index", "bound", "slots", "materials", "positions", "normals", "uvs", "indices", "weights", "weighted")


class Texture:
    __slots__ = ("index", "offset", "flags", "size", "fmt", "mips", "w", "h", "pitch", "cube", "palette")


class Xpr:
    def __init__(self):
        self.data = b""
        self.block2 = 0
        self.mdl = None          # offset of the 'MDL\0' block or None
        self.mdlsize = 0
        self.compact = False     # newer OBJ layout (DOA2U 'A#' costumes)
        self.objs = []
        self.textures = []


SLOT_STRIDE = (0x20, 0x18, 0x28, 0x20)
# compact OBJ: slot 0 pos(3) normal(3) uv(2), slot 2 pos(3) diffuse uv(2) (DOA3 stages' pre-lit geometry, no normals);
# slots 1 and 3 never occur
COMPACT_STRIDE = {0: 0x20, 2: 0x18}


def _texture(i, block2, off, fl, size):
    t = Texture()
    t.index, t.offset, t.flags, t.size = i, block2 + off, fl, size
    t.fmt = (fl >> 8) & 0xFF
    t.mips = (fl >> 16) & 0xF
    t.cube = bool(fl & 4)
    t.pitch = None
    t.palette = None
    lw, lh = (fl >> 20) & 0xF, (fl >> 24) & 0xF
    if lw or lh or not size:
        t.w, t.h = 1 << lw, 1 << lh   # D3DFORMAT_USIZE (width) at bit 20, VSIZE (height) at bit 24
    else:  # linear non-power-of-two: dimensions live in the Size dword
        t.w, t.h = (size & 0xFFF) + 1, ((size >> 12) & 0xFFF) + 1
        t.pitch = (((size >> 24) & 0xFF) + 1) * 64
    return t


def parse_xpr(raw):
    """raw: bytes of an .xpr (scrambled or plain). Returns Xpr with textures and, if present, MDL objects."""
    d = xbox_crypt.decrypt_xpr(raw)
    if d[:4] != b"XPR0":
        # DOAX costumes keep everything plain but overwrite the magic dword
        if len(d) > 24 and d[12:16] == b"\0\0\0\x80" and d[20:24] == b"MDL\0":
            d = b"XPR0" + d[4:]
        else:
            raise ValueError("not an XPR0 file")
    u = lambda o: struct.unpack_from("<I", d, o)[0]
    x = Xpr()
    x.data = d
    x.block2 = u(8)
    # resource directory: user blocks (bit 31: size follows), vertex buffers, textures...
    p = 12
    texents = []
    palettes = []                 # (number of textures seen so far, (palette data offset, entries))
    while p + 4 <= min(len(d), x.block2):
        t = u(p)
        if t == 0xFFFFFFFF:
            break
        if t & 0x80000000:
            size = u(p + 4)
            if d[p + 8:p + 12] == b"MDL\0" and x.mdl is None:
                x.mdl, x.mdlsize = p + 8, size
            p += 8 + size
            continue
        kind = (t >> 16) & 7
        if kind == 4 or kind == 5:      # texture / surface: common, data, lock, format, size
            texents.append((u(p + 4), u(p + 12), u(p + 16)))
            p += 20
        elif kind == 3:                 # palette: normally right after the P8 texture it belongs to
            palettes.append((len(texents), (x.block2 + u(p + 4), (256, 128, 64, 32)[t >> 30])))
            p += 12
        elif kind in (0, 1):            # vertex buffer / index buffer: common, data, lock
            p += 12
        else:
            break
    x.textures = [_texture(i, x.block2, off, fl, sz) for i, (off, fl, sz) in enumerate(texents)]
    for t in x.textures:
        if t.fmt == 0x0B and palettes:   # first palette after the texture, else the last one before it
            after = [pal for pos, pal in palettes if pos > t.index]
            t.palette = after[0] if after else palettes[-1][1]
    if x.mdl is not None:
        _parse_mdl(x, d, u)
    return x


def _parse_mdl(x, d, u):
    objnum = u(x.mdl + 4)
    offs = [u(0x28 + 4 * i) for i in range(objnum)]
    for oi, o in enumerate(offs):
        if d[o:o + 4] != b"OBJ\0":
            raise ValueError("bad OBJ magic at 0x%x" % o)
        end = offs[oi + 1] if oi + 1 < len(offs) else x.mdl + x.mdlsize
        ob = Obj()
        ob.index = oi
        compact = u(o + 8) != 4      # DOA3, DOA1U, DOA2U 'A#': slots at +0x10, bound at +0x50, materials at +0x60
        # blend weights per vertex (DOA2U: 0/1, DOAX: up to 3), stored right after the position. The compact layout
        # has none: its +4 is 0 in characters, 1 in DOA3 stages and 2 in DOA3 effects.
        nw = 0 if compact else u(o + 4)
        nw = nw if nw <= 4 else 0
        ob.weighted = nw > 0
        ob.weights = {}
        ob.materials = []
        if compact:
            x.compact = True
            ob.slots = [struct.unpack_from("<4I", d, o + 0x10 + 16 * s) for s in range(4)]
            ob.bound = struct.unpack_from("<4f", d, o + 0x50)
        else:
            ob.slots = [struct.unpack_from("<4I", d, o + 0x20 + 16 * s) for s in range(4)]
            ob.bound = struct.unpack_from("<4f", d, o + 16)
        ob.positions, ob.normals, ob.uvs, ob.indices = {}, {}, {}, {}
        for s, (vn, vo, inn, io_) in enumerate(ob.slots):
            if vn == 0 or (compact and s not in COMPACT_STRIDE):
                continue
            # every slot: pos(3) weights(nw) then  0: normal(3) uv(2) | 1: diffuse uv(2) |
            # 2: normal(3) uv0(2) uv(2) | 3: diffuse uv0(2) uv(2)   (the last uv pair is the main mapping)
            stride = COMPACT_STRIDE[s] if compact else SLOT_STRIDE[s] + 4 * nw
            raw = np.frombuffer(d, dtype=np.uint8, count=vn * stride, offset=vo).reshape(vn, stride)
            f = np.ascontiguousarray(raw).view("<f4").reshape(vn, -1)
            ob.positions[s] = f[:, 0:3].copy()
            if nw:
                ob.weights[s] = f[:, 3:3 + nw].copy()
            lit = s == 0 if compact else s in (0, 2)
            ob.normals[s] = f[:, 3 + nw:6 + nw].copy() if lit else None
            ob.uvs[s] = f[:, -2:].copy()
            ob.indices[s] = np.frombuffer(d, dtype="<u2", count=inn, offset=io_).astype(np.int64)
        if compact:
            _parse_compact_materials(ob, d, u, o + 0x60, end)
            x.objs.append(ob)
            continue
        q = o + 0x60 + 0x40
        while q + 0x80 <= end:
            # marker 0x8000000n or 0x90000000 (bit 0: alpha blend; 2/3/5/7 also occur, e.g. aya18's helmet visor),
            # size 0x80 + 16 per texture; the zero padding after the last material ends the list
            mid, ms = u(q), u(q + 4)
            if not mid & 0x80000000 or mid & 0x0FFFFFF0 or ms != 0x80 + 16 * u(q + 0x64) or q + ms > end:
                break
            mt = Material()
            mt.matid = mid
            mt.transparent = bool(mid & 1)
            mt.nrm_mode = u(q + 12)
            mt.bound = struct.unpack_from("<4f", d, q + 16)
            f = struct.unpack_from("<17f", d, q + 32)
            mt.diffuse, mt.ambient, mt.specular, mt.emissive = f[0:4], f[4:8], f[8:12], f[12:16]
            mt.power = f[16]
            nimg = u(q + 32 + 68)
            mt.textures = [struct.unpack_from("<4I", d, q + 0x70 + 16 * t) for t in range(nimg)]
            bufnv, istart, itris, _ = struct.unpack_from("<4I", d, q + ms - 16)
            mt.slot = bufnv >> 16
            mt.ind_start, mt.ind_tris = istart, itris
            mt.strips = None
            mt.tex_field = 0
            ob.materials.append(mt)
            q += ms
        x.objs.append(ob)


def _parse_compact_materials(ob, d, u, q, end):
    """Compact OBJ materials (DOA3, DOA1U, DOA2U 'A#'; checked on every DOA3 file, where each texture id then lands in
    the file's texture list and all but one texture of 4741 is used):
    marker, size in dwords, blend, flags | bound 4f | ?, diffuse/ambient/specular/emissive 4f each | power | ntex |
    ntex x 16-byte texture stages (texture id, unit, type, flags), as in the regular layout | strip count | vertex slot |
    strips (bytes, index start, triangle count, cull). Stage id 0x888 is a stage without a texture (the combine step
    of DOA3's three-stage reflective materials: base, reflection map, 0x888). A strip's bytes are (count + 2) x the
    slot's vertex stride. Its cull is 0 unless the material flags have bit 0 set, then mostly D3DCULL_CW / CCW
    (0x900 / 0x901), which match the strip's winding against the stored normals 99%; the viewer orients by the
    normals instead and draws these materials double-sided, as GreedXplorer does. The index data follows the last
    material, after a 0x12345678 marker.
    Alpha blending is bit 0 of the dword at +0x08: set on every material whose texture has alpha (DOA3, DOA1U and
    DOA2U alike). The marker's bit 0, the flag in the regular layout, is never set in DOA1U / DOA2U and in DOA3 sits
    on opaque textures."""
    while q + 0x74 <= end:
        mid, size = u(q), 4 * u(q + 4)
        ntex = u(q + 0x68)
        if mid not in (0x80000000, 0x80000001) or ntex > 16 or size < 0x74 or q + size > end:
            break
        r = q + 0x6C + 16 * ntex
        nrec, slot = u(r), u(r + 4)
        if r + 8 + 16 * nrec > q + size:
            break
        mt = Material()
        mt.matid = mid
        mt.transparent = bool(u(q + 8) & 1)
        mt.nrm_mode = u(q + 0x0C)   # the field GreedXplorer reads for culling, as in the regular layout
        mt.bound = struct.unpack_from("<4f", d, q + 0x10)
        f = struct.unpack_from("<17f", d, q + 0x24)
        mt.diffuse, mt.ambient, mt.specular, mt.emissive = f[0:4], f[4:8], f[8:12], f[12:16]
        mt.power = f[16]
        mt.textures = [struct.unpack_from("<4I", d, q + 0x6C + 16 * t) for t in range(ntex)]
        mt.tex_field = 0
        mt.slot, mt.ind_start, mt.ind_tris = slot, 0, 0
        mt.strips = [(start, count) for _, start, count, _ in
                     (struct.unpack_from("<4I", d, r + 8 + 16 * k) for k in range(nrec)) if 0 < count < 0x10000]
        ob.materials.append(mt)
        q += size


def material_cull(flags, compact=False):
    """Per-material cull mode from the material dword at +0x0C, as GreedXplorer does it (GX_003D.exe 0x48EBB0 /
    0x48EBD4): 0 or 0x900 -> CW, 0x901 -> CCW, anything else -> none. Its CW hides back faces in its mirrored view
    (CULL_BACK here). So only flag 0 is single-sided; thin cloth (bit 0: Ayane's bow, aprons, sleeves) and hair (bit 3)
    show both sides. Hair layering is handled by the viewer's two-pass alpha drawing, not by culling.
    The compact format has no flag values GreedXplorer culls on, so it stays double-sided."""
    if flags == 0x900 or (flags == 0 and not compact):
        return CULL_BACK
    if flags == 0x901:
        return CULL_FRONT
    return CULL_NONE


def obj_geometry(ob, ntex):
    """Merge all slots/materials of an OBJ into one viewer mesh."""
    chunks = []
    for mt in ob.materials:
        s = mt.slot
        if s not in ob.indices:
            continue
        ind = ob.indices[s]
        if mt.strips is None:
            tris = strip_to_tris(ind[mt.ind_start:mt.ind_start + mt.ind_tris + 2])
        else:  # one stitched strip; each draw also covers the 2 stitch indices in front of it
            parts = [strip_to_tris(ind[a:a + n + 4]) for a, n in mt.strips]
            tris = np.concatenate(parts) if parts else np.zeros((0, 3), np.int64)
        if not len(tris) or tris.max() >= len(ob.positions[s]):
            continue
        if mt.strips is not None:  # strip parity is unverified in this format: trust the stored normals instead
            tris = orient_to_normals(ob.positions[s], ob.normals.get(s), tris)
        used, inv = np.unique(tris, return_inverse=True)
        tex = mt.textures[0][mt.tex_field] if mt.textures else -1
        if not 0 <= tex < ntex:
            tex = -1
        # bit 24 of a texture ref's last dword: the texture is a reflection map, sphere-mapped from the normals rather
        # than laid out by the UVs (chrome/sheen images: aya18's helmet dome, Zack's metal; the second, kind-4 stage of
        # two-stage materials). Same bit in the compact format; its pre-lit slot has no normals to map from.
        nrm = ob.normals.get(s)
        env = bool(mt.textures) and bool(mt.textures[0][3] & 0x1000000) and (mt.strips is None or nrm is not None)
        cull = material_cull(mt.nrm_mode, compact=mt.strips is not None)
        if nrm is not None:
            nrm = nrm[used]
        elif mt.strips is not None:   # DOA3's pre-lit stage geometry: light it with normals from its own triangles
            nrm = vertex_normals(ob.positions[s][used], inv.reshape(-1, 3))
        chunks.append(dict(pos=ob.positions[s][used], nrm=nrm, uv=ob.uvs[s][used],
                           tris=inv.reshape(-1, 3),
                           sub=dict(tex=int(tex), transparent=mt.transparent, cull=cull, env=env,
                                    diffuse=[float(v) for v in mt.diffuse])))
    g = merge_geometry(chunks)
    if g is not None:
        g["name"] = "OBJ_%d" % ob.index
    return g


def add_textures(scene, x):
    for t in x.textures:
        scene.add_texture(t.w, t.h, texture.xbox_format_name(t.fmt),
                          (lambda t=t: texture.decode_xbox(x.data, t.offset, t.fmt, t.w, t.h, t.pitch, t.palette)),
                          name="tex%03d" % t.index)


def to_scene(sid, raw, title=None):
    """Meshes at their stored origins + all textures. Callers place parts (e.g. with a GX layout)."""
    x = parse_xpr(raw)
    sc = Scene(sid, title)
    sc.meshes = [obj_geometry(ob, len(x.textures)) for ob in x.objs]
    add_textures(sc, x)
    sc.info = dict(meshes=len(x.objs), textures=len(x.textures), format="XPR0" + (" + MDL" if x.mdl else ""))
    return sc, x
