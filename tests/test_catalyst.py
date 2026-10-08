import os
import struct
import math
import pytest

from exopy.archive import collect_parts, extract
from exopy.catalyst import open_bundle, list_sessions, get_session, laps, lap_data_path
from exopy.telemetry import HEADER_SIZE, parse_lap_file

DEMO_PASSPHRASE = "FF59E1881B4ED01C5C2F5F01890AFF25E9764D27"
DEMO_FIXTURE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../testdata/demo/SupportLogs.tar.gz.gpg.aa")
)

TRACK_BOXES = {
    124: (36.40, 36.50, -77.65, -77.50),  # NCCAR
    64: (36.50, 36.60, -79.30, -79.10),   # Virginia International Raceway
}


@pytest.fixture(scope="module")
def demo_bundle(tmp_path_factory):
    dir_path = str(tmp_path_factory.mktemp("catalyst-test-"))
    parts = collect_parts(DEMO_FIXTURE)
    extract(parts, DEMO_PASSPHRASE, dir_path)
    b = open_bundle(dir_path)
    yield b
    b.close()


def test_list_sessions(demo_bundle):
    sessions = list_sessions(demo_bundle)
    assert len(sessions) == 2
    assert sessions[0].id == 124
    assert sessions[1].id == 64

    by_id = {s.id: s for s in sessions}
    assert by_id[124].track_name == "NCCAR"
    assert by_id[64].track_name == "Virginia International Raceway"
    assert by_id[124].make == "LOTUS"


def test_get_session(demo_bundle):
    s = get_session(demo_bundle, "64")
    assert s.id == 64

    with pytest.raises(ValueError, match="not found"):
        get_session(demo_bundle, "999999")


def test_laps(demo_bundle):
    lap_list = laps(demo_bundle, "124")
    got_nums = {l.lap_num for l in lap_list}
    for l in lap_list:
        assert l.session_id == 124
    for want in (-1, 0, 1, 2):
        assert want in got_nums


def header_count(path: str) -> int:
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < HEADER_SIZE:
        return 0
    return struct.unpack_from("<i", data, 4)[0]


def test_lap_data_parsing(demo_bundle):
    for session_id, (lat_min, lat_max, lon_min, lon_max) in TRACK_BOXES.items():
        lap_list = laps(demo_bundle, str(session_id))
        assert len(lap_list) > 0

        for lap in lap_list:
            if not lap.interp_loc:
                continue

            path = lap_data_path(demo_bundle, lap.interp_loc)
            pts = parse_lap_file(path, lap.lap_duration_ms)

            want_count = header_count(path)
            assert len(pts) == want_count
            assert len(pts) > 0

            prev = -1.0
            for i, p in enumerate(pts):
                assert lat_min <= p.lat <= lat_max, f"session {session_id} lap {lap.lap_num} pt {i} lat {p.lat}"
                assert lon_min <= p.lon <= lon_max, f"session {session_id} lap {lap.lap_num} pt {i} lon {p.lon}"
                assert 0 <= p.speed_mph <= 300, f"session {session_id} lap {lap.lap_num} pt {i} speed {p.speed_mph}"
                assert not math.isnan(p.lat) and not math.isnan(p.speed_mph)
                assert p.time_offset >= prev, f"session {session_id} lap {lap.lap_num} pt {i} non-monotonic"
                prev = p.time_offset

            if lap.lap_num >= 1 and lap.lap_duration_ms > 0:
                last = pts[-1].time_offset
                want_span = lap.lap_duration_ms / 1000.0
                assert want_span * 0.5 <= last <= want_span


def test_lap_data_path_defaults_to_lap_data(demo_bundle):
    path = lap_data_path(demo_bundle, "124_1.bin")
    assert os.path.exists(path)

    with pytest.raises(ValueError, match="not found"):
        lap_data_path(demo_bundle, "does_not_exist.bin")
