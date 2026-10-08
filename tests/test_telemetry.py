import os
import struct
import pytest

from exopy.telemetry import HEADER_SIZE, RECORD_SIZE, parse_lap_file


def write_lap_file(tmp_path, count: int, records: list) -> str:
    buf = bytearray(HEADER_SIZE)
    struct.pack_into("<I", buf, 4, count)
    for r in records:
        buf.extend(r)
    p = os.path.join(tmp_path, "lap.bin")
    with open(p, "wb") as f:
        f.write(buf)
    return p


def record(
    lat: float,
    lon: float,
    speed_mph: float,
    track_usage: float,
    altitude: float,
    accel_long: float,
    accel_lat: float,
    accel_z: float,
    gyro_x: float,
    gyro_y: float,
    gyro_z: float,
) -> bytes:
    r = bytearray(RECORD_SIZE)
    struct.pack_into("<dd", r, 0, lat, lon)
    struct.pack_into("<f", r, 16, speed_mph)
    struct.pack_into(
        "<ffffffff",
        r,
        28,
        track_usage,
        altitude,
        accel_long,
        accel_lat,
        accel_z,
        gyro_x,
        gyro_y,
        gyro_z,
    )
    return bytes(r)


def test_parse_lap_file_decodes_fields(tmp_path):
    rec = record(
        36.5,
        -79.2,  # lat, lon
        100.0,  # speed mph
        0.5,  # track usage -> *100 = 50
        250.0,  # altitude
        9.81,  # accelLong -> /9.81 = 1 G
        -19.62,  # accelLat -> -2 G
        4.905,  # accelZ -> 0.5 G
        0.1,
        0.2,
        0.3,  # gyro
    )
    p = write_lap_file(tmp_path, 1, [rec])
    pts = parse_lap_file(p, 0)
    assert len(pts) == 1
    pt = pts[0]
    assert pytest.approx(pt.lat, abs=1e-9) == 36.5
    assert pytest.approx(pt.lon, abs=1e-9) == -79.2
    assert pytest.approx(pt.speed_mph, abs=1e-3) == 100.0
    assert pytest.approx(pt.track_usage, abs=1e-3) == 50.0
    assert pytest.approx(pt.altitude, abs=1e-3) == 250.0
    assert pytest.approx(pt.accel_long, abs=1e-4) == 1.0
    assert pytest.approx(pt.accel_lat, abs=1e-4) == -2.0
    assert pytest.approx(pt.accel_z, abs=1e-4) == 0.5
    assert pytest.approx(pt.gyro_x, abs=1e-4) == 0.1
    assert pytest.approx(pt.gyro_y, abs=1e-4) == 0.2
    assert pytest.approx(pt.gyro_z, abs=1e-4) == 0.3
    assert pytest.approx(pt.time_offset, abs=1e-9) == 0.0


def test_parse_lap_file_time_step(tmp_path):
    recs = [record(36.5, -79.2, 50, 0, 0, 0, 0, 0, 0, 0, 0) for _ in range(4)]
    p = write_lap_file(tmp_path, 4, recs)
    pts = parse_lap_file(p, 8000)  # 8s over 4 records -> 2s step
    assert len(pts) == 4
    for i, pt in enumerate(pts):
        assert pytest.approx(pt.time_offset, abs=1e-9) == float(i) * 2.0


def test_parse_lap_file_truncated(tmp_path):
    recs = [
        record(36.5, -79.2, 50, 0, 0, 0, 0, 0, 0, 0, 0),
        record(36.5, -79.2, 51, 0, 0, 0, 0, 0, 0, 0, 0),
    ]
    p = write_lap_file(tmp_path, 5, recs)  # claims 5, only 2 present
    pts = parse_lap_file(p, 0)
    assert len(pts) == 2


def test_parse_lap_file_huge_count(tmp_path):
    rec = record(36.5, -79.2, 50, 0, 0, 0, 0, 0, 0, 0, 0)
    p = write_lap_file(tmp_path, 1_000_000_000, [rec])
    pts = parse_lap_file(p, 0)
    assert len(pts) == 1


def test_parse_lap_file_too_small(tmp_path):
    p = os.path.join(tmp_path, "tiny.bin")
    with open(p, "wb") as f:
        f.write(bytes([0, 1, 2, 3]))
    with pytest.raises(ValueError, match="too small"):
        parse_lap_file(p, 0)
