#!/usr/bin/env python3
"""
NoBuildingStability - RuneScape: Dragonwilds mod builder (Python 3 stdlib only).

WHAT THE MOD DOES
  Turns off building stability in Normal and Hard worlds, while leaving
  achievements enabled.

HOW
  The game already has a "No Building Stability" setting, but it can only be
  chosen in Custom/Creative worlds, and achievement unlocks are skipped for
  those two modes. The setting's value is resolved as: the world's saved value
  if there is one, otherwise DA_DifficultySetting_NoBuildingStability's
  PresetDefaults[current mode].

  This mod overrides that one data asset, adding
      PresetDefaults = { Normal: 1.0, Hard: 1.0 }
  so the game's own no-stability path runs while the world stays Normal/Hard.
  Nothing is written to your saves and no game file is modified.

USAGE
  python build_mod.py            build into <game>/RSDragonwilds/Content/Paks/~mods
  python build_mod.py --out DIR  build somewhere else

  Re-run after a game update: the mod replaces a whole asset, so it should be
  rebuilt from the current version. The script stops with an error, rather than
  writing anything, if the asset no longer has the expected layout.

UNINSTALL
  Delete NoBuildingStability_P.pak/.utoc/.ucas from Content/Paks/~mods.
"""
import argparse
import hashlib
import struct
import sys
from pathlib import Path

GAME_ROOT = Path(__file__).resolve().parents[2]
PAKS = GAME_ROOT / "RSDragonwilds" / "Content" / "Paks"
BASE_UTOC = PAKS / "RSDragonwilds-Windows.utoc"
MOD_NAME = "NoBuildingStability_P"

DIFFICULTY_DIR = "RSDragonwilds/Content/Gameplay/DifficultySettings/Player/"
TARGET = DIFFICULTY_DIR + "DA_DifficultySetting_NoBuildingStability.uasset"
# A sibling asset that already uses both enum names; their FName hashes are copied from it.
NAME_DONOR = DIFFICULTY_DIR + "DA_DifficultySetting_PlayerDamageScale.uasset"
NEW_NAMES = ("ESurvivalDifficulty::Normal", "ESurvivalDifficulty::Hard")
PRESET_VALUE = 1.0

MOUNT_POINT = "../../../"
TOC_MAGIC = b"-==--==--==--==-"
TOC_VERSION = 8
TOC_FLAG_INDEXED = 8
CHUNK_TYPE_CONTAINER_HEADER = 6
BLOCK_SIZE = 65536
CHUNK_ALIGN = 4096
NO_INDEX = 0xFFFFFFFF
FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x00000100000001B3
U64 = (1 << 64) - 1


class ModBuildError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ModBuildError(message)


# ---------------------------------------------------------------- reading ----

class BaseContainer:
    """Reader for the game's uncompressed, unencrypted IoStore container."""

    def __init__(self, utoc):
        self.ucas = utoc.with_suffix(".ucas")
        toc = utoc.read_bytes()
        require(toc[:16] == TOC_MAGIC and toc[16] == TOC_VERSION,
                f"unexpected TOC version in {utoc.name}; the game's format has changed")
        header_size, entries, block_count, block_entry_size, method_count, method_len, \
            self.block_size, dir_size, _ = struct.unpack_from("<9I", toc, 20)
        flags = toc[80]
        require(flags == TOC_FLAG_INDEXED and method_count == 0,
                "the game's container is now compressed or encrypted; this builder can't read it")
        seed_count = struct.unpack_from("<I", toc, 84)[0]
        no_hash_count = struct.unpack_from("<I", toc, 96)[0]

        pos = header_size
        self.chunk_ids = [toc[pos + i * 12:pos + i * 12 + 12] for i in range(entries)]
        pos += 12 * entries
        self.offset_lengths = []
        for i in range(entries):
            raw = toc[pos + i * 10:pos + i * 10 + 10]
            self.offset_lengths.append((int.from_bytes(raw[:5], "big"), int.from_bytes(raw[5:], "big")))
        pos += 10 * entries
        pos += 4 * seed_count + 4 * no_hash_count
        self.block_offsets = [
            int.from_bytes(toc[pos + i * block_entry_size:pos + i * block_entry_size + 5], "little")
            for i in range(block_count)
        ]
        pos += block_entry_size * block_count + method_count * method_len
        self.files = _read_directory_index(toc[pos:pos + dir_size])

    def read_chunk(self, index):
        offset, length = self.offset_lengths[index]
        block = offset // self.block_size
        inner = offset % self.block_size
        out = bytearray()
        with open(self.ucas, "rb") as f:
            while len(out) < length:
                f.seek(self.block_offsets[block] + inner)
                out += f.read(min(length - len(out), self.block_size - inner))
                block += 1
                inner = 0
        return bytes(out)

    def read_file(self, path):
        require(path in self.files, f"{path} was not found in the game's container")
        return self.read_chunk(self.files[path])

    def chunk_id_of(self, path):
        return self.chunk_ids[self.files[path]]

    def container_header(self):
        for i, chunk_id in enumerate(self.chunk_ids):
            if chunk_id[11] == CHUNK_TYPE_CONTAINER_HEADER:
                return self.read_chunk(i)
        raise ModBuildError("the game's container has no container header chunk")


def _read_directory_index(data):
    pos = 0

    def fstring():
        nonlocal pos
        length = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        if length == 0:
            return ""
        if length < 0:
            text = data[pos:pos - 2 * length - 2].decode("utf-16-le")
            pos += -2 * length
        else:
            text = data[pos:pos + length - 1].decode("utf-8")
            pos += length
        return text

    def u32_records(width):
        nonlocal pos
        count = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        values = struct.unpack_from(f"<{count * width}I", data, pos)
        pos += count * width * 4
        return values

    mount = fstring()
    dirs = u32_records(4)
    files = u32_records(3)
    count = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    names = [fstring() for _ in range(count)]

    result = {}
    stack = [(0, mount)]
    while stack:
        index, parent = stack.pop()
        name, child, sibling, first_file = dirs[index * 4:index * 4 + 4]
        current = parent if name == NO_INDEX else parent + names[name] + "/"
        if sibling != NO_INDEX:
            stack.append((sibling, parent))
        if child != NO_INDEX:
            stack.append((child, current))
        entry = first_file
        while entry != NO_INDEX:
            file_name, next_file, user_data = files[entry * 3:entry * 3 + 3]
            result[(current + names[file_name]).replace(MOUNT_POINT, "")] = user_data
            entry = next_file
    return result


def package_store_imports(header, package_id):
    """Return (header version, imported package ids) for one package in a container header."""
    signature, version = struct.unpack_from("<II", header, 0)
    require(signature == 0x496F436E, "bad container header signature")
    require(version == 5, f"unsupported container header version {version}")
    pos = 16
    count = struct.unpack_from("<i", header, pos)[0]
    pos += 4
    ids = struct.unpack_from(f"<{count}Q", header, pos)
    pos += 8 * count
    store_size = struct.unpack_from("<i", header, pos)[0]
    pos += 4
    store = header[pos:pos + store_size]
    index = ids.index(package_id)
    import_count, import_offset, shader_count, _ = struct.unpack_from("<iIiI", store, index * 16)
    require(shader_count == 0, "target package unexpectedly references shader maps")
    return struct.unpack_from(f"<{import_count}Q", store, index * 16 + import_offset)


# --------------------------------------------------------------- patching ----

def read_name_batch(package):
    """Return (names, hashes, offset of the first byte after the name strings)."""
    count = struct.unpack_from("<I", package, 0x3C)[0]
    hashes_at = 0x4C
    headers_at = hashes_at + 8 * count
    strings_at = headers_at + 2 * count
    names, hashes = [], []
    pos = strings_at
    for i in range(count):
        length = struct.unpack_from(">H", package, headers_at + i * 2)[0]
        require(length & 0x8000 == 0, "unexpected UTF-16 name in package")
        names.append(package[pos:pos + length].decode("ascii"))
        hashes.append(package[hashes_at + i * 8:hashes_at + i * 8 + 8])
        pos += length
    return names, hashes, pos


def patch_asset(original, donor):
    """Return a copy of the asset with PresetDefaults = {Normal, Hard} added."""
    names, hashes, strings_end = read_name_batch(original)
    donor_names, donor_hashes, _ = read_name_batch(donor)
    require(not set(NEW_NAMES) & set(names), "asset already has per-mode presets; layout has changed")
    for name in NEW_NAMES:
        require(name in donor_names, f"{name} missing from donor asset")

    header_size = struct.unpack_from("<I", original, 4)[0]
    export_map_at = struct.unpack_from("<I", original, 0x20)[0]
    first_section_at = struct.unpack_from("<I", original, 0x18)[0]
    name_count = len(names)

    # Unversioned property header of the data asset: fields 0-6 (field 3 zero-masked),
    # skip 7-8, then fields 9-10.
    exp0 = original[header_size:]
    require(exp0[:5] == b"\x80\x0e\x02\x05\x08", "asset property header has changed; refusing to patch")
    export0_size = struct.unpack_from("<Q", original, export_map_at + 8)[0]
    require(struct.unpack_from("<Q", original, export_map_at)[0] == 0, "unexpected export order")
    export0 = bytearray(exp0[:export0_size])

    # Field 9 (a 22-character id string) directly follows field 6, bDigitalValue == 1.
    marker = struct.pack("<i", 23)
    insert_at = export0.find(marker)
    require(insert_at > 0 and export0[insert_at - 1] == 1, "could not locate PresetDefaults position")
    require(export0.find(marker, insert_at + 1) == -1, "PresetDefaults position is ambiguous")

    new_map = struct.pack("<ii", 0, len(NEW_NAMES))  # NumKeysToRemove, Num
    for i in range(len(NEW_NAMES)):
        new_map += struct.pack("<iif", name_count + i, 0, PRESET_VALUE)  # FName, float

    export0[2:4] = b"\x01\x07"  # skip field 7, then fields 8, 9, 10 (last fragment)
    export0[insert_at:insert_at] = new_map
    grew_by = len(new_map)

    # Rebuild the name batch with the new names appended, so existing indices stay valid.
    new_hashes = list(hashes) + [donor_hashes[donor_names.index(n)] for n in NEW_NAMES]
    new_names = names + list(NEW_NAMES)
    new_name_block = b"".join(new_hashes)
    new_name_block += b"".join(struct.pack(">H", len(n)) for n in new_names)
    new_name_block += "".join(new_names).encode("ascii")

    # Fixed-size summary + counts + hash version, then the block above.
    head = bytearray(original[:0x4C])
    struct.pack_into("<II", head, 0x3C, len(new_names), sum(len(n) for n in new_names))
    after_names = 0x4C + len(new_name_block)

    # Padding so the sections that follow stay 8-byte aligned.
    old_pad = struct.unpack_from("<Q", original, strings_end)[0]
    require((strings_end + 8 + old_pad) % 8 == 0, "unexpected padding after name batch")
    bulk_map_at = strings_end + 8 + old_pad
    require(struct.unpack_from("<Q", original, bulk_map_at)[0] == 0, "asset has bulk data; layout has changed")
    require(bulk_map_at + 8 == first_section_at, "unexpected data between names and first section")
    new_pad = (8 - (after_names + 8) % 8) % 8
    pad_block = struct.pack("<Q", new_pad) + b"\0" * new_pad + struct.pack("<Q", 0)

    new_first_section = after_names + len(pad_block)
    delta = new_first_section - first_section_at
    require(delta % 8 == 0, "section shift would break alignment")

    # All section offsets move by the same amount.
    struct.pack_into("<I", head, 4, header_size + delta)
    for field in range(0x18, 0x3C, 4):
        value = struct.unpack_from("<I", head, field)[0]
        struct.pack_into("<I", head, field, value + delta)

    sections = bytearray(original[first_section_at:header_size])
    # Export map: export 0 grew, so export 1 starts later.
    map_in_sections = export_map_at - first_section_at
    entry_size = 72
    struct.pack_into("<Q", sections, map_in_sections + 8, export0_size + grew_by)
    next_entry = map_in_sections + entry_size
    next_offset = struct.unpack_from("<Q", sections, next_entry)[0]
    require(next_offset == export0_size, "unexpected second export offset")
    struct.pack_into("<Q", sections, next_entry, next_offset + grew_by)

    return bytes(head) + new_name_block + pad_block + bytes(sections) + bytes(export0) + exp0[export0_size:]


# --------------------------------------------------------------- writing ----

def fstring(text):
    raw = text.encode("ascii") + b"\0"
    return struct.pack("<i", len(raw)) + raw


def build_directory_index(path, toc_index):
    parts = path.split("/")
    directories, file_name = parts[:-1], parts[-1]
    strings = directories + [file_name]
    dir_entries = []
    # Root entry, then one entry per nested directory; the last one holds the file.
    for depth in range(len(directories) + 1):
        name = NO_INDEX if depth == 0 else depth - 1
        child = depth + 1 if depth < len(directories) else NO_INDEX
        first_file = 0 if depth == len(directories) else NO_INDEX
        dir_entries.append((name, child, NO_INDEX, first_file))
    out = fstring(MOUNT_POINT)
    out += struct.pack("<I", len(dir_entries))
    for entry in dir_entries:
        out += struct.pack("<4I", *entry)
    out += struct.pack("<I", 1) + struct.pack("<3I", len(strings) - 1, NO_INDEX, toc_index)
    out += struct.pack("<I", len(strings))
    for s in strings:
        out += fstring(s)
    return out


def hash_chunk_id(seed, chunk_id):
    value = seed if seed else FNV_OFFSET
    for byte in chunk_id:
        value = ((value * FNV_PRIME) & U64) ^ byte
    return value


def pick_container_id(asset_chunk_id):
    """Pick an id whose header chunk hashes to the opposite bucket from the asset chunk.

    With a table of size 2 only the hash's low bit matters, and for FNV that bit
    depends on the id's byte parity, not the seed. So two chunks of equal parity
    can't be separated by any seed; choosing the container id avoids that.
    """
    for salt in range(256):
        digest = hashlib.sha1(f"{MOD_NAME}:{salt}".encode()).digest()
        container_id = digest[:8]
        header_chunk_id = container_id + b"\0\0\0" + bytes([CHUNK_TYPE_CONTAINER_HEADER])
        if hash_chunk_id(0, header_chunk_id) % 2 != hash_chunk_id(0, asset_chunk_id) % 2:
            return container_id, header_chunk_id
    raise ModBuildError("could not generate chunk hash table")


def build_chunk_table(chunk_ids):
    """Return the seed table: each chunk is alone in its bucket, so seeds index slots directly."""
    seeds = [0] * len(chunk_ids)
    for slot, chunk_id in enumerate(chunk_ids):
        seeds[hash_chunk_id(0, chunk_id) % len(chunk_ids)] = -slot - 1
    return seeds


def write_container(out_dir, asset_path, asset_chunk_id, asset, imports):
    container_id_bytes, header_chunk_id = pick_container_id(asset_chunk_id)
    container_id = struct.unpack("<Q", container_id_bytes)[0]

    package_id = struct.unpack("<Q", asset_chunk_id[:8])[0]
    store = struct.pack("<iIiI", len(imports), 16, 0, 0)
    store += struct.pack(f"<{len(imports)}Q", *imports)
    container_header = struct.pack("<IIQ", 0x496F436E, 5, container_id)
    container_header += struct.pack("<iQ", 1, package_id)
    container_header += struct.pack("<i", len(store)) + store
    container_header += struct.pack("<ii", 0, 0)      # optional segment ids / entries
    container_header += struct.pack("<iii", 0, 0, 0)  # redirect names, localized, redirects
    soft_refs_at = len(container_header) + 16
    container_header += struct.pack("<qq", soft_refs_at, 4)
    container_header += struct.pack("<I", 0)          # no soft package references

    chunks = {asset_chunk_id: asset, header_chunk_id: container_header}
    order = list(chunks)
    seeds = build_chunk_table(order)

    ucas = bytearray()
    offset_lengths, block_entries = b"", b""
    logical = 0
    for chunk_id in order:
        data = chunks[chunk_id]
        require(len(data) <= BLOCK_SIZE, "chunk larger than one block")
        offset_lengths += logical.to_bytes(5, "big") + len(data).to_bytes(5, "big")
        block_entries += len(ucas).to_bytes(5, "little")
        block_entries += len(data).to_bytes(3, "little") * 2 + b"\0"
        ucas += data
        ucas += b"\0" * (-len(ucas) % CHUNK_ALIGN)
        logical += BLOCK_SIZE

    directory = build_directory_index(asset_path, order.index(asset_chunk_id))
    header = bytearray(144)
    header[:16] = TOC_MAGIC
    header[16] = TOC_VERSION
    struct.pack_into("<9I", header, 20, 144, len(order), len(order), 12, 0, 32, BLOCK_SIZE, len(directory), 1)
    header[56:64] = container_id_bytes
    header[80] = TOC_FLAG_INDEXED
    struct.pack_into("<I", header, 84, len(seeds))
    struct.pack_into("<Q", header, 88, U64)  # partition size: unlimited

    toc = bytes(header) + b"".join(order) + offset_lengths
    toc += struct.pack(f"<{len(seeds)}i", *seeds)
    toc += block_entries + directory
    toc += b"\0" * (24 * len(order))  # per-chunk hash metadata; not read at runtime

    (out_dir / f"{MOD_NAME}.utoc").write_bytes(toc)
    (out_dir / f"{MOD_NAME}.ucas").write_bytes(bytes(ucas))


def fnv64_path(path, seed):
    value = (FNV_OFFSET + seed) & U64
    for byte in path.lower().encode("utf-16-le"):
        value = ((value ^ byte) * FNV_PRIME) & U64
    return value


def write_pak(out_dir):
    """Every IoStore container needs a sibling .pak; this one holds a small note."""
    directory = "RSDragonwilds/Content/Mods/NoBuildingStability/"
    file_name = "about.txt"
    data = b"NoBuildingStability: enables the game's no-stability path in Normal and Hard worlds.\n"
    # In-file entry record: offset, size, raw size, method, sha1, encrypted flag, block size.
    record = struct.pack("<qqqI", 0, len(data), len(data), 0)
    record += hashlib.sha1(data).digest() + b"\0" + struct.pack("<I", 0)
    body = record + data

    seed = int.from_bytes(hashlib.sha1(MOD_NAME.encode()).digest()[8:12], "little")
    encoded_entry = struct.pack("<III", 0xE0000000, 0, len(data))  # all 32-bit fields, uncompressed

    # The directory index lists the root and every parent folder, even when empty.
    parts = directory.rstrip("/").split("/")
    listed = ["/"] + ["/".join(parts[:depth]) + "/" for depth in range(1, len(parts) + 1)]
    full_directory_index = struct.pack("<i", len(listed))
    for name in listed:
        full_directory_index += fstring(name)
        if name == directory:
            full_directory_index += struct.pack("<i", 1) + fstring(file_name) + struct.pack("<i", 0)
        else:
            full_directory_index += struct.pack("<i", 0)

    # The path hash section is the hash table followed by a (here unpruned) directory index.
    path_hash_index = struct.pack("<i", 1) + struct.pack("<Qi", fnv64_path(directory + file_name, seed), 0)
    path_hash_index += full_directory_index

    index_at = len(body)
    primary_size = (
        len(fstring(MOUNT_POINT)) + 4 + 8      # mount point, entry count, path hash seed
        + 4 + 8 + 8 + 20 + 4 + 8 + 8 + 20      # both secondary index descriptors
        + 4 + len(encoded_entry) + 4           # encoded entries, unencoded file count
    )
    path_hash_at = index_at + primary_size
    directory_at = path_hash_at + len(path_hash_index)

    primary = fstring(MOUNT_POINT) + struct.pack("<iQ", 1, seed)
    primary += struct.pack("<iqq", 1, path_hash_at, len(path_hash_index))
    primary += hashlib.sha1(path_hash_index).digest()
    primary += struct.pack("<iqq", 1, directory_at, len(full_directory_index))
    primary += hashlib.sha1(full_directory_index).digest()
    primary += struct.pack("<i", len(encoded_entry)) + encoded_entry + struct.pack("<i", 0)
    require(len(primary) == primary_size, "pak index size mismatch")

    footer = b"\0" * 16 + b"\0"  # encryption key guid, encrypted-index flag
    footer += struct.pack("<Iiqq", 0x5A6F12E1, 11, index_at, len(primary))
    footer += hashlib.sha1(primary).digest()
    footer += b"\0" * 160        # compression method names: none

    (out_dir / f"{MOD_NAME}.pak").write_bytes(body + primary + path_hash_index + full_directory_index + footer)


def main():
    parser = argparse.ArgumentParser(description="Build the NoBuildingStability mod.")
    parser.add_argument("--out", type=Path, default=PAKS / "~mods", help="output folder")
    args = parser.parse_args()

    base = BaseContainer(BASE_UTOC)
    asset = patch_asset(base.read_file(TARGET), base.read_file(NAME_DONOR))
    chunk_id = base.chunk_id_of(TARGET)
    package_id = struct.unpack("<Q", chunk_id[:8])[0]
    imports = package_store_imports(base.container_header(), package_id)

    args.out.mkdir(parents=True, exist_ok=True)
    write_container(args.out, TARGET, chunk_id, asset, imports)
    write_pak(args.out)
    print(f"Built {MOD_NAME}.pak/.utoc/.ucas in {args.out}")


if __name__ == "__main__":
    try:
        main()
    except ModBuildError as error:
        sys.exit(f"Build stopped, nothing usable was written: {error}")
