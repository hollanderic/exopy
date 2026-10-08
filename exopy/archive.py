"""Package archive turns a Catalyst SupportLogs archive (split, GPG-encrypted, gzipped tar) into an extracted directory on disk."""

import glob
import io
import os
import tarfile
import warnings
import zlib
from dataclasses import dataclass, field
from typing import List

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*TripleDES.*")
warnings.filterwarnings("ignore", message=".*Camellia.*")
warnings.filterwarnings("ignore", message=".*CFB.*")

import pgpy
from pgpy.packet.packets import SKESessionKey, _decrypt



@dataclass
class Result:
    files: int = 0
    partial_recovery: bool = False
    notes: List[str] = field(default_factory=list)


def is_split_part(path: str) -> bool:
    """is_split_part reports whether a path ends in a two-letter split suffix like ".aa"."""
    ext = os.path.splitext(path)[1]
    if len(ext) != 3 or not ext.startswith("."):
        return False
    return 'a' <= ext[1] <= 'z' and 'a' <= ext[2] <= 'z'


def collect_parts(input_path: str) -> List[str]:
    """CollectParts resolves an input path to the ordered list of encrypted parts."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"[Errno 2] No such file or directory: '{input_path}'")

    parts: List[str] = []
    if os.path.isdir(input_path):
        single = glob.glob(os.path.join(input_path, "*.gpg"))
        split = glob.glob(os.path.join(input_path, "*.gpg.*"))
        parts.extend(single)
        parts.extend(split)
    elif is_split_part(input_path):
        prefix = os.path.splitext(input_path)[0]
        parts = glob.glob(prefix + ".*")
    else:
        parts = [input_path]

    if not parts:
        raise ValueError(f"no .gpg parts found at {input_path}")

    parts.sort()
    return parts


def decrypted_bytes(parts: List[str], passphrase: str) -> bytes:
    """decrypted_bytes concatenates the parts and returns the decrypted OpenPGP plaintext."""
    concat_data = bytearray()
    for p in parts:
        with open(p, "rb") as f:
            concat_data.extend(f.read())

    msg = pgpy.PGPMessage.from_blob(bytes(concat_data))
    skesk = next((sk for sk in msg._sessionkeys if isinstance(sk, SKESessionKey)), None)
    if skesk is None:
        raise ValueError("No symmetric key encrypted session key packet found")

    try:
        symalg, key = skesk.decrypt_sk(passphrase)
    except Exception as e:
        raise ValueError("incorrect GPG passphrase") from e

    # Decrypt ciphertext packet directly (unauthenticated/salvage mode)
    pt = _decrypt(bytes(msg._message.ct), bytes(key), symalg)

    if len(pt) < 18:
        raise ValueError("decrypted stream too short")

    data = pt[18:]
    # Strip Literal Data Packet (Tag 11) header if present
    if len(data) > 0 and data[0] in (0xAC, 0xAD, 0xAE, 0xAF):
        fmt_idx = 1 + (1 if data[0] == 0xAC else 2 if data[0] == 0xAD else 4 if data[0] == 0xAE else 0)
        if len(data) > fmt_idx + 1:
            name_len = data[fmt_idx + 1]
            hdr_len = fmt_idx + 2 + name_len + 4
            if len(data) >= hdr_len:
                data = data[hdr_len:]

    return bytes(data)


def extract(parts: List[str], passphrase: str, out_dir: str) -> Result:
    """Extract decrypts the parts and unpacks the gzipped tar into out_dir."""
    payload = decrypted_bytes(parts, passphrase)
    os.makedirs(out_dir, exist_ok=True)

    res = Result()

    # Decompress gzip payload using zlib decompressobj (31 = 16 + 15 for gzip window)
    dobj = zlib.decompressobj(31)
    try:
        tar_bytes = dobj.decompress(payload)
    except Exception as e:
        if res.files == 0:
            raise ValueError(f"gunzip: {e}") from e
        tar_bytes = b""

    tf = tarfile.open(fileobj=io.BytesIO(tar_bytes))
    out_dir_path = os.path.abspath(out_dir)

    while True:
        try:
            member = tf.next()
            if member is None:
                break
        except Exception as e:
            if res.files > 0:
                res.partial_recovery = True
                res.notes.append(
                    f"archive truncated; extracted {res.files} complete files before the cut-off"
                )
                break
            raise ValueError(f"untar: {e}") from e

        target_path = os.path.abspath(os.path.join(out_dir, member.name))
        try:
            rel = os.path.relpath(target_path, out_dir_path)
        except ValueError:
            rel = ".."

        if rel.startswith("..") or rel == "..":
            raise ValueError(f"unsafe path in archive: {member.name}")

        if member.isdir():
            os.makedirs(target_path, exist_ok=True)
        elif member.isfile():
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            try:
                f = tf.extractfile(member)
                if f is not None:
                    with open(target_path, "wb") as out_f:
                        out_f.write(f.read())
                    res.files += 1
            except Exception as e:
                if res.files > 0:
                    res.partial_recovery = True
                    res.notes.append(
                        f"archive truncated; extracted {res.files} complete files before the cut-off"
                    )
                    break
                raise ValueError(f"untar: {e}") from e

    return res
