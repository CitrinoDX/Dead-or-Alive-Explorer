"""Texture decoding shared by every game: DXT1/3/5 + BC5, Xbox (NV2A) swizzled/linear formats,
Xbox 360 tiled + byte-swapped formats, and a dependency-free PNG encoder."""
import struct, zlib
import numpy as np


# ----------------------------------------------------------------- block compression
def _rgb565(v):
    r = ((v >> 11) & 31) * 255 // 31
    g = ((v >> 5) & 63) * 255 // 63
    b = (v & 31) * 255 // 31
    return r, g, b


def _color_blocks(blocks, dxt1):
    """blocks: (N,8) uint8 color blocks -> (N,16,4) rgba"""
    c0 = blocks[:, 0].astype(np.uint16) | (blocks[:, 1].astype(np.uint16) << 8)
    c1 = blocks[:, 2].astype(np.uint16) | (blocks[:, 3].astype(np.uint16) << 8)
    r0, g0, b0 = _rgb565(c0)
    r1, g1, b1 = _rgb565(c1)
    p0 = np.stack([r0, g0, b0], 1).astype(np.int32)
    p1 = np.stack([r1, g1, b1], 1).astype(np.int32)
    four = (c0 > c1) if dxt1 else np.ones(len(c0), dtype=bool)
    p2 = np.where(four[:, None], (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(four[:, None], (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)  # N,4,3
    alpha_pal = np.full((len(c0), 4), 255, dtype=np.int32)
    if dxt1:
        alpha_pal[:, 3] = np.where(four, 255, 0)
    bits = (blocks[:, 4].astype(np.uint32) | (blocks[:, 5].astype(np.uint32) << 8) |
            (blocks[:, 6].astype(np.uint32) << 16) | (blocks[:, 7].astype(np.uint32) << 24))
    sel = (bits[:, None] >> (2 * np.arange(16, dtype=np.uint32))[None, :]) & 3  # N,16
    rgb = np.take_along_axis(pal, sel[:, :, None].astype(np.int64).repeat(3, 2), axis=1)
    a = np.take_along_axis(alpha_pal, sel.astype(np.int64), axis=1)
    return np.concatenate([rgb, a[:, :, None]], 2)


def _alpha_blocks(raw):
    """raw: (N,8) uint8 interpolated-alpha blocks (DXT5 alpha / BC4 / one half of BC5) -> (N,16) int"""
    n = len(raw)
    a0 = raw[:, 0].astype(np.int32)
    a1 = raw[:, 1].astype(np.int32)
    ab = np.zeros(n, dtype=np.uint64)
    for i in range(6):
        ab |= raw[:, 2 + i].astype(np.uint64) << np.uint64(8 * i)
    sel = ((ab[:, None] >> (3 * np.arange(16, dtype=np.uint64))[None, :]) & np.uint64(7)).astype(np.int64)
    pal = np.zeros((n, 8), dtype=np.int32)
    pal[:, 0], pal[:, 1] = a0, a1
    gt = a0 > a1
    for i in range(1, 7):
        pal[:, i + 1] = np.where(gt, ((7 - i) * a0 + i * a1) // 7,
                                 np.where(i <= 4, ((5 - i) * a0 + i * a1) // 5, 0))
    pal[:, 7] = np.where(gt, pal[:, 7], 255)
    return np.take_along_axis(pal, sel, axis=1)


def _blocks_to_image(px, w, h):
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    img = px.reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return np.clip(img, 0, 255).astype(np.uint8)[:h, :w]


def block_bytes(kind):
    return 8 if kind in ("DXT1", "BC4") else 16


def decode_block(data, w, h, kind, offset=0):
    """kind: DXT1 / DXT3 / DXT5 / BC5. data holds linear 4x4 blocks (little-endian)."""
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    n = bw * bh
    bb = block_bytes(kind)
    raw = np.frombuffer(data, dtype=np.uint8, count=n * bb, offset=offset).reshape(n, bb)
    if kind == "DXT1":
        px = _color_blocks(raw, True)
    elif kind == "BC5":
        x = _alpha_blocks(raw[:, 0:8]).astype(np.float32) / 127.5 - 1
        y = _alpha_blocks(raw[:, 8:16]).astype(np.float32) / 127.5 - 1
        z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
        px = np.stack([(x + 1) * 127.5, (y + 1) * 127.5, (z + 1) * 127.5, np.full_like(x, 255)], 2)
    else:
        px = _color_blocks(raw[:, 8:], False)
        if kind == "DXT3":
            a = np.zeros((n, 16), dtype=np.int32)
            for i in range(8):
                a[:, 2 * i] = (raw[:, i] & 15) * 17
                a[:, 2 * i + 1] = (raw[:, i] >> 4) * 17
        else:
            a = _alpha_blocks(raw[:, 0:8])
        px[:, :, 3] = a
    return _blocks_to_image(px, w, h)


# ----------------------------------------------------------------- Xbox (NV2A)
def _spread(n, bits):
    out = np.zeros_like(n)
    for i in range(bits):
        out |= ((n >> i) & 1) << (2 * i)
    return out


def xbox_unswizzle_index(w, h):
    """Xbox morton swizzle: (h,w) array of source texel indices (w, h powers of two)."""
    xs, ys = np.meshgrid(np.arange(w, dtype=np.int64), np.arange(h, dtype=np.int64))
    lw, lh = w.bit_length() - 1, h.bit_length() - 1
    m = min(lw, lh)
    idx = (_spread(xs, m) | (_spread(ys, m) << 1)) if m else xs * 0
    if lw > m:
        idx |= (xs >> m) << (2 * m)
    if lh > m:
        idx |= (ys >> m) << (2 * m)
    return idx


def _expand(v, bits):
    return (v.astype(np.int32) * 255 // ((1 << bits) - 1)).astype(np.uint8)


def _unpack16(v, layout):
    """v uint16 array -> (...,4) rgba for 16-bit layouts"""
    if layout == "565":
        r, g, b = _expand(v >> 11 & 31, 5), _expand(v >> 5 & 63, 6), _expand(v & 31, 5)
        a = np.full_like(r, 255)
    elif layout in ("1555", "x555"):
        r, g, b = _expand(v >> 10 & 31, 5), _expand(v >> 5 & 31, 5), _expand(v & 31, 5)
        a = (np.where(v >> 15, 255, 0).astype(np.uint8) if layout == "1555" else np.full_like(r, 255))
    elif layout == "4444":
        a, r, g, b = _expand(v >> 12 & 15, 4), _expand(v >> 8 & 15, 4), _expand(v >> 4 & 15, 4), _expand(v & 15, 4)
    else:  # A8L8
        l, a = (v & 255).astype(np.uint8), (v >> 8).astype(np.uint8)
        r = g = b = l
    return np.stack([r, g, b, a], -1)


# format id -> (name, kind, swizzled)
XBOX_FORMATS = {
    0x00: ("L8", "l8", True), 0x01: ("AL8", "l8", True), 0x02: ("A1R5G5B5", "1555", True),
    0x03: ("X1R5G5B5", "x555", True), 0x04: ("A4R4G4B4", "4444", True), 0x05: ("R5G6B5", "565", True),
    0x06: ("A8R8G8B8", "argb", True), 0x07: ("X8R8G8B8", "xrgb", True), 0x0B: ("P8", "p8", True),
    0x0C: ("DXT1", "DXT1", False), 0x0E: ("DXT3", "DXT3", False), 0x0F: ("DXT5", "DXT5", False),
    0x10: ("LIN_A1R5G5B5", "1555", False), 0x11: ("LIN_R5G6B5", "565", False),
    0x12: ("LIN_A8R8G8B8", "argb", False), 0x13: ("LIN_L8", "l8", False), 0x19: ("A8", "a8", True),
    0x1A: ("A8L8", "a8l8", True), 0x1C: ("LIN_X1R5G5B5", "x555", False), 0x1D: ("LIN_A4R4G4B4", "4444", False),
    0x1E: ("LIN_X8R8G8B8", "xrgb", False), 0x1F: ("LIN_A8", "a8", False), 0x20: ("LIN_A8L8", "a8l8", False),
    0x28: ("V8U8", "v8u8", True), 0x3A: ("A8B8G8R8", "abgr", True), 0x3F: ("LIN_A8B8G8R8", "abgr", False),
}
_BPP = {"l8": 1, "a8": 1, "p8": 1, "1555": 2, "x555": 2, "4444": 2, "565": 2, "a8l8": 2, "v8u8": 2,
        "argb": 4, "xrgb": 4, "abgr": 4}


def xbox_format_name(fmt):
    return XBOX_FORMATS.get(fmt, ("0x%02X" % fmt,))[0]


def decode_xbox(data, offset, fmt, w, h, pitch=None, palette=None):
    """Decode mip 0 of an Xbox texture. Returns (h,w,4) uint8 RGBA, or None if the format is unsupported.
    palette: (offset, entries) of the D3DPalette (BGRA dwords) for P8 textures."""
    spec = XBOX_FORMATS.get(fmt)
    if not spec:
        return None
    _, kind, swz = spec
    if kind in ("DXT1", "DXT3", "DXT5"):
        return decode_block(data, w, h, kind, offset)
    if kind == "p8" and palette is None:
        return None
    bpp = _BPP[kind]
    if not swz and pitch and pitch != w * bpp:  # linear with row padding
        rows = np.frombuffer(data, dtype=np.uint8, count=pitch * h, offset=offset).reshape(h, pitch)[:, :w * bpp]
        raw = np.ascontiguousarray(rows).reshape(-1)
    else:
        raw = np.frombuffer(data, dtype=np.uint8, count=w * h * bpp, offset=offset)
    if bpp == 4:
        px = raw.reshape(-1, 4)
    elif bpp == 2:
        px = raw.view("<u2")
    else:
        px = raw
    if swz:
        px = px[xbox_unswizzle_index(w, h).reshape(-1)]
    if kind in ("argb", "xrgb"):
        out = px.reshape(h, w, 4)[:, :, [2, 1, 0, 3]].copy()
        if kind == "xrgb":
            out[:, :, 3] = 255
    elif kind == "abgr":
        out = px.reshape(h, w, 4).copy()
    elif kind == "p8":
        poff, n = palette
        pal = np.zeros((256, 4), np.uint8)
        pal[:n] = np.frombuffer(data, np.uint8, count=n * 4, offset=poff).reshape(n, 4)[:, [2, 1, 0, 3]]
        out = pal[px.reshape(h, w)]
    elif kind == "v8u8":  # signed bump offsets, shown as a normal-map-style image
        uv = px.view(np.int8).reshape(h, w, 2).astype(np.int16) + 128
        out = np.full((h, w, 4), 255, np.uint8)
        out[:, :, 0], out[:, :, 1] = uv[:, :, 0], uv[:, :, 1]
    elif kind == "l8":
        out = np.repeat(px.reshape(h, w, 1), 4, 2).copy()
        out[:, :, 3] = 255
    elif kind == "a8":
        out = np.full((h, w, 4), 255, np.uint8)
        out[:, :, 3] = px.reshape(h, w)
    elif kind == "a8l8":
        out = _unpack16(px, "a8l8").reshape(h, w, 4)
    else:
        out = _unpack16(px, kind).reshape(h, w, 4)
    return out


# ----------------------------------------------------------------- Xbox 360 (Xenos)
X360_FORMATS = {  # GPUTEXTUREFORMAT -> (name, bytes per block, block dim)
    0x02: ("L8", 1, 1), 0x06: ("A8R8G8B8", 4, 1), 0x12: ("DXT1", 8, 4), 0x13: ("DXT3", 16, 4),
    0x14: ("DXT5", 16, 4), 0x31: ("BC5", 16, 4), 0x3B: ("BC4", 8, 4),
}


def x360_tiled_offsets(bw, bh, bpb):
    """Block index (in units of bpb-byte blocks) of every (y,x) block of a tiled 360 surface."""
    log_bpp = (bpb >> 2) + ((bpb >> 1) >> (bpb >> 2))
    aw = (bw + 31) & ~31
    x, y = np.meshgrid(np.arange(bw, dtype=np.int64), np.arange(bh, dtype=np.int64))
    macro = ((x >> 5) + (y >> 5) * (aw >> 5)) << (log_bpp + 7)
    micro = ((x & 7) + ((y & 6) << 2)) << log_bpp
    off = macro + ((micro & ~15) << 1) + (micro & 15) + ((y & 8) << (3 + log_bpp)) + ((y & 1) << 4)
    off = (((off & ~511) << 3) + ((off & 448) << 2) + (off & 63) + ((y & 16) << 7) +
           (((((y & 8) >> 2) + (x >> 3)) & 3) << 6))
    return off >> log_bpp


def _endian_swap(raw, endian):
    if endian == 1:    # 8-in-16
        return raw.reshape(-1, 2)[:, ::-1].reshape(-1)
    if endian == 2:    # 8-in-32
        return raw.reshape(-1, 4)[:, ::-1].reshape(-1)
    if endian == 3:    # 16-in-32
        return raw.reshape(-1, 2, 2)[:, ::-1, :].reshape(-1)
    return raw


def x360_format_name(fmt):
    return X360_FORMATS.get(fmt, ("0x%02X" % fmt,))[0]


def decode_x360(data, offset, fmt, endian, w, h, tiled=True):
    """Decode mip 0 of a 360 texture (fmt = low 6 bits of fetch-constant dword 1, endian = bits 6-7)."""
    spec = X360_FORMATS.get(fmt)
    if not spec:
        return None
    name, bpb, dim = spec
    bw, bh = (w + dim - 1) // dim, (h + dim - 1) // dim
    if tiled:
        offs = x360_tiled_offsets(bw, bh, bpb).reshape(-1)
        need = int(offs.max() + 1) * bpb
    else:
        offs = np.arange(bw * bh, dtype=np.int64)
        need = bw * bh * bpb
    src = np.frombuffer(data, dtype=np.uint8, count=min(need, len(data) - offset), offset=offset)
    if len(src) < need:
        src = np.concatenate([src, np.zeros(need - len(src), np.uint8)])
    blocks = src.reshape(-1, bpb)[offs].reshape(-1)
    blocks = _endian_swap(blocks, endian)
    if dim == 4:
        return decode_block(blocks.tobytes(), w, h, name)
    if name == "L8":
        out = np.repeat(blocks.reshape(bh, bw, 1), 4, 2).copy()
        out[:, :, 3] = 255
        return out[:h, :w]
    px = blocks.reshape(bh, bw, 4)  # little-endian ARGB dword after the swap: B G R A
    return px[:h, :w][:, :, [2, 1, 0, 3]].copy()


# ----------------------------------------------------------------- output
def alpha_class(rgba):
    """'opaque' (no transparency at all), 'mask' (pixels are essentially fully clear or fully solid: alpha-test it)
    or 'blend' (real translucency)."""
    a = rgba[:, :, 3]
    if a.min() >= 250:
        return "opaque"
    return "mask" if ((a > 8) & (a < 247)).mean() < 0.03 else "blend"


def placeholder(w, h):
    img = np.full((max(1, h), max(1, w), 4), [255, 0, 255, 255], dtype=np.uint8)
    return img


def png_bytes(rgba):
    h, w = rgba.shape[:2]
    rgba = np.ascontiguousarray(rgba, dtype=np.uint8)
    raw = np.zeros((h, w * 4 + 1), np.uint8)
    raw[:, 1:] = rgba.reshape(h, w * 4)

    def chunk(t, c):
        return struct.pack(">I", len(c)) + t + c + struct.pack(">I", zlib.crc32(t + c) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw.tobytes(), 6)) + chunk(b"IEND", b""))
