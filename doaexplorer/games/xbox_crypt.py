"""DOA2U scramble layer, reverse-engineered from GreedXplorer's unpacked code (verified byte-exact).
Standard MT19937; keystream = output + 0x31415926, XORed over little-endian dwords.
(GreedXplorer's 'custom' tempering masks reduce to the standard ones once shifted into 32 bits.)"""
import struct
import numpy as np

M32 = 0xFFFFFFFF


def _mt_stream(seed, count):
    """count keystream words (MT19937 output + 0x31415926) as a uint32 numpy array."""
    mt = np.zeros(624, np.uint64)
    mt[0] = seed & M32
    for i in range(1, 624):
        p = int(mt[i - 1])
        mt[i] = (0x6C078965 * (p ^ (p >> 30)) + i) & M32
    mt = mt.astype(np.uint32)
    out = np.empty(count, np.uint32)
    n = 0
    while n < count:
        # twist, vectorised in slices whose inputs are already final: mt[i] needs the new mt[i-227]
        for a, b in ((0, 227), (227, 454), (454, 623)):
            y = (mt[a:b] & 0x80000000) | (mt[a + 1:b + 1] & 0x7FFFFFFF)
            src = mt[a + 397:b + 397] if a == 0 else mt[a - 227:b - 227]
            mt[a:b] = src ^ (y >> 1) ^ np.where(y & 1, np.uint32(0x9908B0DF), np.uint32(0))
        y = (mt[623] & 0x80000000) | (mt[0] & 0x7FFFFFFF)
        mt[623] = mt[396] ^ (y >> 1) ^ (0x9908B0DF if y & 1 else 0)
        y = mt.copy()
        y ^= y >> 11
        y ^= (y << 7) & np.uint32(0x9D2C5680)
        y ^= (y << 15) & np.uint32(0xEFC60000)
        y ^= y >> 18
        k = min(624, count - n)
        out[n:n + k] = y[:k]
        n += k
    return out + np.uint32(0x31415926)


def _xor(buf, start, count, seed):
    out = bytearray(buf)
    if count <= 0:
        return out
    v = np.frombuffer(bytes(out[start:start + 4 * count]), "<u4") ^ _mt_stream(seed, count)
    out[start:start + 4 * count] = v.astype("<u4").tobytes()
    return out


def is_scrambled_xpr(data):
    return len(data) >= 12 and (struct.unpack_from("<I", data, 0)[0] & 0xFFFFFF00) == 0x306EA300


def decrypt_xpr(data):
    """Return plain XPR0 bytes (unchanged if not scrambled)."""
    if not is_scrambled_xpr(data):
        return data
    seed = struct.unpack_from("<I", data, 0)[0] ^ 0x30525058
    size = struct.unpack_from("<I", data, 4)[0]
    count = (min(len(data), size) >> 2) - 3
    out = _xor(data, 12, count, seed)
    out[0:4] = b"XPR0"
    return bytes(out)


def is_scrambled_cat(data):
    return len(data) >= 20 and (struct.unpack_from("<I", data, 0)[0] & 0xFFFFFF00) == 0x003CF300


def decrypt_cat(data):
    if not is_scrambled_cat(data):
        return data
    seed = struct.unpack_from("<I", data, 0)[0] ^ 0x20
    count = min(struct.unpack_from("<I", data, 16)[0] >> 2, (len(data) - 20) // 4)
    out = _xor(data, 20, count, seed)
    struct.pack_into("<I", out, 0, 0x20)
    return bytes(out)
