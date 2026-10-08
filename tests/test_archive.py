import os
import pytest

from exopy.archive import collect_parts, extract

DEMO_PASSPHRASE = "FF59E1881B4ED01C5C2F5F01890AFF25E9764D27"
DEMO_FIXTURE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../testdata/demo/SupportLogs.tar.gz.gpg.aa")
)


def test_extract_full_archive(tmp_path):
    parts = collect_parts(DEMO_FIXTURE)
    res = extract(parts, DEMO_PASSPHRASE, str(tmp_path))
    assert not res.partial_recovery
    assert res.files > 0


def test_extract_recovers_truncated_archive(tmp_path):
    with open(DEMO_FIXTURE, "rb") as f:
        full = f.read()

    # Cut off last 40% to simulate incomplete upload
    trunc_path = os.path.join(tmp_path, "trunc.gpg")
    with open(trunc_path, "wb") as f:
        f.write(full[: len(full) * 60 // 100])

    parts = collect_parts(trunc_path)
    out_dir = os.path.join(tmp_path, "out")
    res = extract(parts, DEMO_PASSPHRASE, out_dir)

    assert res.partial_recovery
    assert res.files > 0
