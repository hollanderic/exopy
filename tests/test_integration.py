import io
import os
import pytest

from exopy.archive import collect_parts, extract
from exopy.catalyst import open_bundle, list_sessions, laps
from exopy.export import session_csv, SpeedUnit
from exopy.cli import DEFAULT_PASSPHRASE

DEMO_FIXTURE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../testdata/demo/SupportLogs.tar.gz.gpg.aa")
)


def test_demo_fixture(tmp_path):
    parts = collect_parts(DEMO_FIXTURE)
    res = extract(parts, DEFAULT_PASSPHRASE, str(tmp_path))
    assert res.files > 0

    with open_bundle(str(tmp_path)) as b:
        sessions = list_sessions(b)
        assert len(sessions) == 2

        by_id = {s.id: s for s in sessions}
        assert 124 in by_id
        assert 64 in by_id
        assert by_id[124].track_name == "NCCAR"

        lap_list = laps(b, "124")
        assert len(lap_list) > 0

        buf = io.StringIO()
        stats = session_csv(buf, b, lap_list, SpeedUnit.METERS_PER_SECOND)
        assert stats.rows > 0

        out = buf.getvalue()
        lines = out.splitlines()

        assert lines[0].startswith("Lap,Time,Lap Time,")
        assert len(lines) == stats.rows + 1
