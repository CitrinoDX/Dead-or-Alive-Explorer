"""Dead or Alive Xtreme 2 (Xbox 360): XPR2/TPR models in chr / werone / wertwo / itm / boat / stg / avt .afs, read
straight from the disc image or an extracted folder.
The nine girls share five skeletons (Kasumi and Ayane; Helena and Lisa; Hitomi, Kokoro and Lei Fang; Christie; Tina),
and so do their bodies apart from the neck. Swimsuits <owner>_<type>_<letter>_m carry the outfit once per body type, a
separate node tree each; the 14 gifts from Zack carry only the owner's fit, and Leifang's qipao and Kasumi's sailor fuku
come as one file per body type. Each tree is matched to the body type whose joints it repeats, and only the owner's fit
is shown. Swimsuits are listed by their shop name (SWIMSUITS); the file name stays in the info line.
Bodies (<code>1) have no head. The heads <code><style><wet> are listed by hairstyle (HAIR): the second letter B is the
wet head, the same hairstyle lying flatter with shorter bangs.
Outfits (the character picker) put one girl's body, any head and any swimsuit with a fit for her body type together:
the head file's root node goes on the body's head node (object 1; the eyes then land on the body's eye nodes within
3 mm, 13 mm for Lisa, whose skeleton is Helena's), and the swimsuit's fit already sits in body space.
Every body carries two pairs of feet: flat ones (ankle, foot, toe joint and toes under each shin) and, as separate root
objects, a one-piece foot tilted 18 degrees toes-down with its own ankle piece, the swap set of the body's .cat. The
tilted pair is for heels. No swimsuit has shoes: footwear is the 18 ankle accessories and the bunny suit's heels in
itm.afs, each followed by a .cat that puts each shoe on a foot bone with a matrix. A pair is heels when it fits the tilted
feet better than the flat ones (10-13 mm off them; flat shoes sit 12-17 mm off the flat feet). Bodies show the flat
feet, outfits the pair their shoes need; the other pair is a hidden group.
Some pieces of each fit are loose objects outside its tree (rigid cups and bows): a fit's objects form one run of
object indices, and its loose pieces sit at the same place in or just before every run. A loose tree split off a fit
(Tina's bottom in vht_ch_a) keeps its other nodes inside that fit's run. Pieces stored once (bead rows, tassel chains,
helper quads, ornaments kept with the middle fit only) are shared props, shown with every fit."""
import collections, os, re, struct
import numpy as np
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
# a fitted copy repeats its body type's joints exactly (0.0000); the nearest other body type is 7 mm off
FIT_TOL = 0.002
# chr.afs head <code><style><wet> -> hairstyle by its first letter; Tina, Lisa, Christie and Kokoro have one hairstyle
HAIR = {
    "vks": {"A": "Long hair down", "B": "Braid with yellow bows", "C": "High ponytail with ribbons", "D": "Low ponytail"},
    "vay": {"A": "With ribbon", "B": "Without ribbon"},
    "vht": {"A": "Pink headband", "B": "No headband"},
    "vle": {"A": "Long straight hair", "B": "Braided buns"},
    "vhe": {"A": "Ponytail with big blue bow", "B": "Ponytail with small bow"},
    "vco": {"B": "Other face texture"},
}
HEAD_NOTES = {
    "vhtAB": "same shapes as the dry Pink headband head: this hairstyle has no real wet version",
    "vcoBA": "same shapes as the dry head; only the face texture differs (ears painted in). What the game uses it for is unknown",
}
# swimsuit file name -> shop names of its repeats in archive order. The qipao and sailor fuku files are one per body type,
# named after a girl of that type, and all carry the same names.
QIPAO = ["Ostrich", "Grebe", "Thunderbird", "Ptarmigan", "Thrush"]
SAILOR = ["Dandelion", "Cherry Blossom"]
QIPAO_FILES = ("vks_on_p_m", "vle_on_i_m", "vhe_on_r_m", "vtn_on_s_m", "vcr_on_u_m")
SAILOR_FILES = ("vks_sk_f_m", "vht_sk_k_m", "vhe_sk_i_m", "vtn_sk_j_m", "vcr_sk_l_m")
# whose shop sells a swimsuit, where that is not the file prefix
SHOP_OWNER = {"vay_dl_i_m": "vls", "vcr_vs_b_m": "vls", "vco_dl_g_m": "vtn", "vtn_on_m_m": "vcr",
              **dict.fromkeys(QIPAO_FILES, "vle"), **dict.fromkeys(SAILOR_FILES, "vks")}
OUTFIT = "outfit:"   # outfit:<code>+<head entry>+<swimsuit entry, or nothing>, made up by the character picker
NECK = 21            # the body object that differs between girls of one body type
# body objects, the same in all nine bodies: per side ankle, foot, toe joint and toes; the tilted ankle and foot for heels
FLAT_FEET = (3, 9, 13, 19, 22, 28, 32, 38)
HEEL_FEET = (4, 10, 23, 29)
HEEL_PARENT = {10: 17, 4: 10, 29: 36, 23: 29}   # where the game swaps them in: foot under the shin, ankle under the foot
FOOT_OBJ = {3: 9, 9: 28}                        # foot bone in a shoe's .cat -> the body object on that bone
SHOES = ("acc_ank_", "zgra_bny_")               # itm.afs footwear: the ankle accessories, the bunny suit's heels
SWIMSUITS = {
    # gifts from Zack, the only character-specific swimsuits
    "vay_cs_b_m": ["Raccoon"], "vco_cs_i_m": ["Shiba"], "vco_cs_j_m": ["Citron", "Cassis"], "vcr_cs_g_m": ["Panther"],
    "vhe_cs_d_m": ["White Cat"], "vht_cs_f_m": ["Bear"], "vks_cs_a_m": ["Rabbit"],
    "vks_hn_i_m": ["Gentian", "Azalea", "Thistle"], "vle_cs_c_m": ["Panda"], "vls_cs_h_m": ["Leopard"],
    "vtn_cs_e_m": ["Black Cat"],
    **dict.fromkeys(QIPAO_FILES, QIPAO),
    **dict.fromkeys(SAILOR_FILES, SAILOR),
    # the rest fit every body type. A few sets sit under another girl's prefix than the shop that sells them (noted).
    # *_sk_* pairs and Helena's / Kokoro's sarong sets: the larger file (with the skirt or sarong) comes first.
    "vay_ch_g_m": ["Oberon", "Efreet", "Carbunkle"],
    "vay_ch_k_m": ["Peri", "Unicorn", "Lubin"],
    "vay_dl_d_m": ["Kerberos", "Sandman", "Titania", "Brownie", "Leprechaun", "Hippogriff", "Pooka"],
    "vay_dl_f_m": ["Nymph", "Kikimora", "Cait Sith", "Lamina", "Cu Sith"],
    "vay_dl_i_m": ["Brigit", "Jono", "Ishtar", "Bellona", "Thaleia"],   # Lisa's
    "vay_on_k_m": ["Echo", "Habetrot", "Roane"],
    "vay_sk_d_m": ["Elf", "Ariel", "Maridah", "Meliae", "Apsaras", "Shylph"],
    "vay_sp_f_m": ["Merrow", "Nixie", "Cuchulain"],
    "vay_wi_c_m": ["Valkyrie", "Impets", "Cluricaune", "Griffon", "Gremlin"],
    "vco_ch_b_m": ["Orange", "Sweetie", "Grapefruit"],
    "vco_ch_c_m": ["Apple", "Star Fruit", "Sweet Cherry", "Pineapple"],
    "vco_ch_f_m": ["Peach", "Raspberry", "Kiwifruit"],
    "vco_dl_g_m": ["Bellatrix", "Alcyone", "Fomalhaut", "Taygeta", "Alphard"],   # Tina's
    "vco_dl_h_m": ["Cranberry", "Grape", "Blueberry", "Prune", "Fig"],
    # each crop top twice: the second copy is the wet shirt (see-through texture)
    "vco_sh_e_m": ["Strawberry", "Watermelon", "Melon", "Strawberry (wet)", "Watermelon (wet)", "Melon (wet)"],
    "vco_sh_f_m": ["Coconut", "Shekwasha", "Muscat"],
    "vco_sk_c_m": ["Banana", "Lime", "Papaya", "Lemon", "Mango", "Quince", "Lychee", "Camu Camu"],
    "vco_sp_b_m": ["Guava", "Apricot", "Durian", "Plum"],
    "vcr_ch_e_m": ["Turquoise", "Jade", "Bloodstone"],
    "vcr_cm_c_m": ["Zircon", "Beryl", "Serpentine"],
    "vcr_hn_c_m": ["Ruby", "Emerald", "Cat's Eye", "Orthoclase"],
    "vcr_hn_h_m": ["Obsidian", "Tourmaline", "Topaz"],
    "vcr_on_g_m": ["Black Pearl", "Jasper", "Azurite"],
    "vcr_on_n_m": ["Diamond", "Aquamarine", "Sapphire"],
    "vcr_sp_c_m": ["Quartz", "Sardonyx", "Ametrine"],
    "vcr_tk_f_m": ["Pearl", "Citrine", "Onyx"],
    "vcr_vs_b_m": ["Venus"],   # Lisa's
    "vcr_wi_a_m": ["Fluorite", "Moonstone", "Carnelian"],
    "vhe_cm_a_m": ["Rob Roy", "Olympic", "Valencia"],
    "vhe_dl_k_m": ["Manhattan", "Tequila Sunrise", "Mint Frappe"],
    "vhe_dl_l_m": ["Godfather", "Brandy Alexander", "Knock Out"],
    "vhe_hn_b_m": ["Gin Buck", "Matador", "Bronx"],
    "vhe_on_c_m": ["Mai-Tai", "Polonaise", "Shandy", "Blue Lagoon"],
    "vhe_on_d_m": ["Moscow Mule", "Kir Royal", "Habana Beach"],
    "vhe_on_l_m": ["Rusty Nail", "Monte Carlo", "Mimosa"],
    "vhe_sh_a_m": ["Bull Shot", "Stinger", "Mojito"],
    "vhe_sk_a_m": ["Affinity", "Panache", "Bourbonella", "Papagena", "Balalaika", "Singapore Sling"],
    "vht_ch_a_m": ["Aries", "Southern Cross", "Virgo"],
    "vht_hn_e_m": ["Scorpion", "Colt", "Fox"],
    "vht_hn_g_m": ["Aquarius", "Marlin", "Puppy"],
    "vht_on_e_m": ["Andromeda", "Meteor", "Cygnus", "Corona"],
    "vht_sh_d_m": ["Coma", "Mensa", "Octans", "Antlia"],
    "vht_sh_g_m": ["Lupus", "Auriga", "Ara"],
    "vht_sk_b_m": ["Whale", "Pegasus", "Cancri"],
    "vht_sk_g_m": ["Crux", "Delphinus", "Indus", "Bootes"],
    "vht_sp_g_m": ["Cetus", "Lacerta", "Apus"],
    "vht_sp_h_m": ["Cealum", "Sculpter", "Grus"],
    "vks_ch_d_m": ["Rhododendron", "Wisteria", "Magnolia"],
    "vks_cm_b_m": ["Lilac", "Cattleya", "Acacia", "Dogwood"],
    "vks_dl_e_m": ["Violet", "Sunflower", "Orchid", "Lavender"],
    "vks_dl_m_m": ["Geranium", "Balsam", "Peony", "Crocus"],
    "vks_hn_d_m": ["Cyclamen", "Amaryllis", "Daisy"],
    "vks_on_o_m": ["Pink", "Sasanqua", "Gerbera", "Anemone", "Gardenia"],
    "vks_sp_d_m": ["Hydrangea", "Marguerite", "Pansy"],
    "vks_wi_b_m": ["Olive", "Hyacinth", "Tulip", "Lily"],
    "vle_ch_j_m": ["Whydah", "Grackle", "Shrike"],
    "vle_dl_a_m": ["Parakeet", "Starling", "Peacock"],
    "vle_hn_a_m": ["Robin", "Canary", "Goldcrest"],
    "vle_hn_f_m": ["Ibis", "Auk", "Moa"],
    "vle_on_f_m": ["Finch", "Rooster", "Loon"],
    "vle_sh_b_m": ["Pipit", "Condor", "Hawk"],
    "vle_sk_h_m": ["Bunting", "Partridge", "Grosbeak"],
    "vle_tk_c_m": ["Bush Warbler", "Cardinal", "Nene"],
    "vle_tk_d_m": ["Stork", "Garuda", "Roc"],
    "vls_dl_b_m": ["Isis", "Sculd", "Parvati"],
    "vls_dl_j_m": ["Sati", "Calliope", "Frigg"],
    "vls_dl_n_m": ["Morrigan", "Daphne", "Atropos"],
    "vls_on_b_m": ["Melpomene", "Aglaia", "Verdandi"],
    "vls_on_h_m": ["Io", "Europa", "Juno"],
    "vls_on_j_m": ["Mach", "Astarte", "Eirene"],
    "vls_sp_a_m": ["Thebe", "Leda", "Ceres"],
    "vls_tk_a_m": ["Saga", "Nemesis", "Memphis"],
    "vls_vs_a_m": ["Fortune"],
    "vls_vs_c_m": ["Arthemis"],
    "vtn_ch_h_m": ["Electra", "Mirfak", "Prometheus", "Alshain"],
    "vtn_ch_i_m": ["Sirius", "Capella", "Altair"],
    "vtn_dl_c_m": ["Alioth", "Meglez", "Porrima"],
    "vtn_on_a_m": ["Pleione", "Mulifein", "Wezn"],
    "vtn_on_m_m": ["Tanzanite", "Nephrite", "Variscite", "Malachite", "Howlite"],   # Christie's
    "vtn_on_y_m": ["Alnile", "Deneb", "Scheat"],
    "vtn_sh_c_m": ["Schedar", "Calf", "Ruchbah"],
    "vtn_sp_e_m": ["Polaris", "Mirzam", "Aludra"],
    "vtn_tk_b_m": ["Procyon", "Castor", "Regulus"],
    "vtn_tk_e_m": ["Pleiades", "Aldebaran", "Mira"],
}


def hierarchies(t):
    """-> [(node list positions with the root first, (n,3) joint positions)] for each separate node tree, in file order"""
    n = len(t.nodes)
    glob, root = [None] * n, [None] * n

    def walk(i, depth=0):
        if glob[i] is None:
            p = t.nodes[i]["parent"]
            if p >= n or depth > 64:
                glob[i], root[i] = t.nodes[i]["m"], i
            else:
                walk(p, depth + 1)
                glob[i], root[i] = glob[p] @ t.nodes[i]["m"], root[p]
    by = {}
    for i in range(n):
        walk(i)
        by.setdefault(root[i], []).append(i)
    trees = [[r] + [i for i in v if i != r] for r, v in sorted(by.items(), key=lambda kv: kv[1][0])]
    return [(v, np.array([glob[i][:3, 3] for i in v])) for v in trees]


def foot_attach(cat):
    """footwear .cat: (object, bone, row-vector 4x4) records from +0x18 until object -1 -> {object: (bone, 4x4)}"""
    out, p = {}, 0x18
    while cat[:4] == b"CAT\0" and p + 72 <= len(cat):
        obj, bone = struct.unpack_from(">ii", cat, p)
        if obj < 0:
            break
        out[obj] = (bone, np.array(struct.unpack_from(">16f", cat, p + 8), np.float64).reshape(4, 4).T)
        p += 72
    return out


def show_feet(sc, t, heels, group):
    """Show one pair of a body scene's feet in group (the tilted pair for heels) and file the other as a hidden group;
    the tilted pieces' bones go where the game swaps them in. Call before anything is merged into the body scene."""
    for p in sc.parts:
        if p["mesh"] in FLAT_FEET + HEEL_FEET:
            flat = p["mesh"] in FLAT_FEET
            spare = flat == heels
            p["group"] = ("Flat feet" if flat else "Feet for heels") if spare else group
            p["visible"] = not spare
    node_of = {n["idx"]: i for i, n in enumerate(t.nodes)}
    for o, parent in HEEL_PARENT.items():
        if o in node_of and parent in node_of:
            sc.bones[node_of[o]]["parent"] = node_of[parent]


def chr_label(stem):
    """chr.afs <code>1 -> 'Body', <code><style><wet> -> 'Head: <hairstyle>', with ' (wet)' for the B heads"""
    rest = stem[3:]
    if len(rest) != 2:
        return "Body" if rest == "1" else "body " + rest
    style = HAIR.get(stem[:3], {}).get(rest[0])
    return "Head" + (": " + style if style else "") + (" (wet)" if rest[1] == "B" else "")


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
        self.bodies, self.heads = {}, {}   # girl code -> chr entry of her body / of her heads
        self.shoes = []                    # footwear entries (SHOES)
        repeat, shoe_no = collections.Counter(), collections.Counter()
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
                    label = chr_label(stem)
                shop = SWIMSUITS.get(stem, ())
                if repeat[stem] < len(shop):
                    label = shop[repeat[stem]]
                repeat[stem] += 1
                if arch == "itm" and stem.startswith(SHOES):   # the archive names all 18 ankle accessories acc_ank_
                    kind = "Ankle accessory" if stem == SHOES[0] else "Bunny heels"
                    shoe_no[kind] += 1
                    label = "%s %d" % (kind, shoe_no[kind])
                eid = "%s:%d" % (arch, i)
                self.entries[eid] = dict(archive=arch, index=i, char=char, section=section, label=label, name=nm,
                                         stem=stem, size=afs.size(i))
                if arch == "itm" and stem.startswith(SHOES):
                    self.shoes.append(eid)
                if arch == "chr" and char:
                    if stem[3:] == "1":
                        self.bodies[char] = eid
                    else:
                        self.heads.setdefault(char, []).append(eid)
        self._tree = None
        self._types = None
        self._dress = None
        self._feet = None
        self._heels = {}

    def body_types(self):
        """[(label, codes, joints)]: the girls grouped by identical skeletons, read from their <code>1.tpr bodies"""
        if self._types is None:
            chr_, types = self.afs.get("chr"), []
            for c in NAMES:
                i = chr_.find(c + "1.tpr") if chr_ else None
                if i is None:
                    continue
                joints = max(hierarchies(tpr.parse_tpr(chr_.read(i))), key=lambda h: len(h[0]))[1]
                for ty in types:
                    if len(ty[1]) == len(joints) and np.abs(ty[1] - joints).max() < 1e-4:
                        ty[0].append(c)
                        break
                else:
                    types.append(([c], joints))
            self._types = [(" / ".join(self.names[c] for c in codes), codes, j) for codes, j in types]
        return self._types

    def type_of(self, code):
        """the body type label a girl belongs to ('Kasumi / Ayane')"""
        return next(label for label, codes, _ in self.body_types() if code in codes)

    def match_trees(self, t):
        """[(nodes, joints, (label, codes) of the body type it fits, or None)] for each node tree of a swimsuit"""
        out = []
        for nodes, joints in hierarchies(t):
            best = None
            for label, codes, B in self.body_types():
                d = np.linalg.norm(B[:, None] - joints[None], axis=2).min(1).max()   # every body joint is repeated
                if d < FIT_TOL and (best is None or d < best[0]):
                    best = (d, label, codes)
            out.append((nodes, joints, best and best[1:]))
        return out

    def group_fits(self, sc, t, owner):
        """Swimsuits: name each node tree after the body type it fits ('Fit: Kasumi / Ayane'), file the loose pieces
        with their fit (see the module notes), show the owner's fit and the props, hide the other fits. Bare bones (most
        of each tree) hang off the nearest part above them, else any part of their tree, so the skeleton view hides them
        with their fit."""
        node_of = {n["idx"]: i for i, n in enumerate(t.nodes)}
        trees, fits, loose = [], [], []
        for nodes, joints, best in self.match_trees(t):
            trees.append((nodes, joints))
            idx = [t.nodes[i]["idx"] for i in nodes]
            if best:
                fits.append(dict(group="Fit: " + best[0], codes=best[1], nodes=nodes, lo=min(idx), hi=max(idx)))
            else:
                loose.append((nodes, idx[1:] or idx))   # a loose tree's root can sit far from its other nodes
        if not fits:
            return
        fits.sort(key=lambda f: f["lo"])
        tree_of = {i: f["group"] for f in fits for i in f["nodes"]}
        placed = []
        for nodes, idx in loose:
            k = next((k for k, f in enumerate(fits) if f["hi"] >= min(idx)), None)
            split = k is not None and len(nodes) > 1 and all(fits[k]["lo"] < i <= fits[k]["hi"] for i in idx)
            placed.append((nodes, k, None if k is None else min(idx) - fits[k]["lo"], split))
        every = collections.Counter(off for _, k, off, _ in placed if k is not None)
        for nodes, k, off, split in placed:
            group = fits[k]["group"] if split or (k is not None and every[off] == len(fits)) else "Props"
            for i in nodes:
                tree_of[i] = group
        mine = [f["group"] for f in fits if owner in f["codes"]] or [fits[0]["group"]]
        for p in sc.parts:
            p["group"] = tree_of.get(node_of.get(p["mesh"]), "Props")
            p["visible"] = p["group"] in (mine[0], "Props")
        order = sorted(range(len(sc.parts)), key=lambda j: not sc.parts[j]["visible"])
        new = {j: k for k, j in enumerate(order)}
        sc.parts = [sc.parts[j] for j in order]
        for b in sc.bones:
            if b["part"] is not None:
                b["part"] = new[b["part"]]
        part_at = {node_of.get(p["mesh"]): j for j, p in enumerate(sc.parts)}
        for nodes, _ in trees:
            first = next((part_at[i] for i in nodes if i in part_at), None)
            for i in nodes:
                a = sc.bones[i]
                for _ in range(64):
                    if a["part"] is not None or a["parent"] < 0:
                        break
                    a = sc.bones[a["parent"]]
                sc.bones[i]["part"] = first if a["part"] is None else a["part"]
        sc.info["fits"] = ", ".join(f["group"][5:] for f in fits)
        if len(fits) > 1:
            sc.note = "%d fitted copies, one per body type - showing %s; the others are hidden groups in the parts panel" % (
                len(fits), mine[0][5:])
        else:
            sc.note = "fitted to %s only" % fits[0]["group"][5:]

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

    def dress(self):
        """The character picker's lists: per girl her body, her heads and every swimsuit with a fit for her body type
        (read from the swimsuits' node trees once, a few seconds), each with the girl whose shop sells it."""
        if self._dress is None:
            suits = {c: [] for c in self.bodies}
            for eid, e in self.entries.items():
                if e["archive"] not in ("werone", "wertwo") or not e["char"]:
                    continue
                t = tpr.parse_tpr(self.afs[e["archive"]].read(e["index"]))
                wearers = {c for _, _, fit in self.match_trees(t) if fit for c in fit[1]}
                for c in wearers & set(suits):
                    suits[c].append(dict(id=eid, label=e["label"], owner=SHOP_OWNER.get(e["stem"], e["char"])))
            stem = lambda eid: self.entries[eid]["stem"]   # AA (first hairstyle, dry) first
            self._dress = dict(girls=[dict(code=c, name=self.names[c], body=self.bodies[c],
                                           heads=[dict(id=h, label=self.entries[h]["label"])
                                                  for h in sorted(self.heads.get(c, []), key=stem)],
                                           suits=sorted(suits[c], key=lambda s: s["label"].lower()))
                                      for c in sorted(self.bodies, key=lambda c: self.names[c])],
                               shoes=[dict(id=s, label=self.entries[s]["label"], heels=self.heels(s)) for s in self.shoes])
        return self._dress

    def put_on_shoes(self, sid, B):
        """A pair of shoes on a body with node matrices B (tpr.global_matrices) -> (shoe scene, {object: matrix}): each
        shoe on the body's foot object, by the .cat that follows the model. Objects the .cat leaves out are not worn."""
        e = self.entries[sid]
        afs = self.afs[e["archive"]]
        ss, st = tpr.to_scene(sid, afs.read(e["index"]))
        S = tpr.global_matrices(st)
        return ss, {o: B[FOOT_OBJ[b]] @ m @ S[o] for o, (b, m) in foot_attach(afs.read(e["index"] + 1)).items()
                    if b in FOOT_OBJ and o in S and ss.meshes[o] is not None}

    def heels(self, sid):
        """True when a pair of shoes fits the tilted feet better than the flat ones: median distance of its vertices to the
        nearest foot vertex, worn on the first body (every body type gives the same answer)"""
        if sid not in self._heels:
            if self._feet is None:
                b = self.entries[next(iter(self.bodies.values()))]
                sc, t = tpr.to_scene(b["stem"], self.afs["chr"].read(b["index"]))
                B = tpr.global_matrices(t)
                world = lambda objs: np.concatenate([sc.meshes[o]["pos"] @ B[o][:3, :3].T + B[o][:3, 3] for o in objs])
                self._feet = (B, world(FLAT_FEET)[::2], world(HEEL_FEET)[::2])
            B, flat, tilt = self._feet
            ss, X = self.put_on_shoes(sid, B)
            p = np.concatenate([ss.meshes[o]["pos"] @ m[:3, :3].T + m[:3, 3] for o, m in X.items()])
            p = p[::max(1, len(p) // 600)]
            near = lambda q: np.median(np.linalg.norm(p[:, None] - q[None], axis=2).min(1))
            self._heels[sid] = bool(X) and bool(near(tilt) < near(flat))
        return self._heels[sid]

    def load_outfit(self, sid):
        """outfit:<code>+<head>+<swimsuit>[+<shoes>]: her body, the head on her head node, the swimsuit's fit for her body
        type, the shoes on her feet (her tilted feet for heels). The swimsuit and shoes add no bones: the fit repeats the
        body's skeleton."""
        code, hid, wid, *rest = sid[len(OUTFIT):].split("+")
        shoes = rest[0] if rest else ""
        chr_, b, h = self.afs["chr"], self.entries[self.bodies[code]], self.entries[hid]
        sc, t = tpr.to_scene(sid, chr_.read(b["index"]))
        for p in sc.parts:
            p["group"] = "Body"
        heels = bool(shoes) and self.heels(shoes)
        show_feet(sc, t, heels, "Body")
        B = tpr.global_matrices(t)
        J = B[1]   # the head node: object 1 (meshless, a 3-vertex stub in Hitomi's body)
        hs, ht = tpr.to_scene(hid, chr_.read(h["index"]))
        root = next(n["idx"] for n in ht.nodes if n["parent"] >= len(ht.nodes))
        X = J @ np.linalg.inv(tpr.global_matrices(ht)[root])
        nb = len(sc.bones)
        sc.merge(hs, "head ", lambda p: ("Head", True, X @ p["m"]))
        neck = next(i for i, n in enumerate(t.nodes) if n["idx"] == 1)
        for bone in sc.bones[nb:]:
            if bone["parent"] < 0:
                bone["parent"] = neck
        who, head = self.names[code], h["label"] + ("" if h["char"] == code else " (%s's)" % self.names[h["char"]])
        files = ["chr.afs #%d (%s)" % (b["index"], b["name"]), "#%d (%s)" % (h["index"], h["name"])]
        suit, notes = "no swimsuit", []
        if h["char"] != code and self.type_of(h["char"]) == self.type_of(code):
            # bodies of one type differ only in the neck piece: take the head owner's, which meets her head
            o = self.entries[self.bodies[h["char"]]]
            os_, _ = tpr.to_scene(o["stem"], chr_.read(o["index"]))
            n = len(sc.parts)
            sc.merge(os_, "neck ", lambda p: ("Body", True, p["m"]) if p["mesh"] == NECK else None, bones=False)
            next(p for p in sc.parts[:n] if p["mesh"] == NECK)["mesh"] = sc.parts[n]["mesh"]
            del sc.parts[n:]
            files.insert(1, "#%d (%s, neck)" % (o["index"], o["name"]))
        elif h["char"] != code:
            notes.append("head swap across body types: the neck is %s's, so the join and skin tone may not match" % who)
        if wid:
            w = self.entries[wid]
            ws = self.load(wid, wearer=code)
            mine = "Fit: " + self.type_of(code)
            if not any(p["group"] == mine for p in ws.parts):
                notes.append("%s has no fit for %s's body type; showing its %s fit" % (w["label"], who, ws.info.get("fits")))
            sc.merge(ws, "suit ", lambda p: ("Swimsuit" if p["group"] != "Props" else "Swimsuit props", True, p["m"])
                     if p["visible"] else None, bones=False)
            suit = w["label"]
            files.append("%s.afs #%d (%s)" % (w["archive"], w["index"], w["name"]))
        shoe = ""
        if shoes:
            s = self.entries[shoes]
            ss, X = self.put_on_shoes(shoes, B)
            sc.merge(ss, "shoes ", lambda p: ("Shoes", True, X[p["mesh"]]) if p["mesh"] in X else None, bones=False)
            shoe = s["label"]
            files.append("itm.afs #%d (%s)" % (s["index"], s["name"]))
            if heels:
                notes.append("heels: her tilted feet are shown, the flat ones are a hidden group")
        sc.title = "%s - %s - %s" % (who, head, suit) + (" - " + shoe if shoe else "")
        sc.export_name = re.sub(r"[^0-9A-Za-z]+", "_", "%s %s %s %s" % (who, head.replace("Head: ", ""), suit, shoe)).strip("_")
        sc.note = "; ".join(notes)
        sc.info.update(meshes=sum(g is not None for g in sc.meshes), textures=len(sc.textures), archive=" + ".join(files))
        return sc

    def load(self, sid, wearer=None):
        """wearer: whose fit a swimsuit shows (default its owner)"""
        if sid.startswith(OUTFIT):
            return self.load_outfit(sid)
        e = self.entries[sid]
        raw = self.afs[e["archive"]].read(e["index"])
        who = self.names.get(e["char"], "") if e["char"] else e["section"]
        sc, t = tpr.to_scene(sid, raw, "%s - %s" % (who, e["label"]))
        sc.info["archive"] = "%s.afs #%d (%s)" % (e["archive"], e["index"], e["name"])
        if not t.objs:
            sc.note = "texture bundle (no meshes)"
        elif e["stem"] in HEAD_NOTES:
            sc.note = HEAD_NOTES[e["stem"]]
        elif not t.nodes:
            sc.note = "no node hierarchy - parts shown at their stored origin"
        elif e["archive"] in ("werone", "wertwo"):
            self.group_fits(sc, t, wearer or e["char"])
        elif sid in self.bodies.values():
            show_feet(sc, t, False, "All")
            sc.note = "the tilted feet for heels are a hidden group in the parts panel"
        return sc
