"""Package telemetry decodes binary lap records."""

import struct
from dataclasses import dataclass
from typing import List

HEADER_SIZE = 20
RECORD_SIZE = 76


@dataclass
class TelemetryPoint:
    time_offset: float  # seconds since lap start
    lat: float
    lon: float
    speed_mph: float
    track_usage: float  # percent
    altitude: float  # meters
    accel_long: float  # G
    accel_lat: float  # G
    accel_z: float  # G
    gyro_x: float  # rad/s
    gyro_y: float  # rad/s
    gyro_z: float  # rad/s


def parse_lap_file(path: str, lap_duration_ms: int = 0) -> List[TelemetryPoint]:
    """ParseLapFile decodes a binary lap-data file."""
    with open(path, "rb") as f:
        data = f.read()

    if len(data) < HEADER_SIZE:
        raise ValueError(f"lap file {path} too small ({len(data)} bytes)")

    count = struct.unpack_from("<i", data, 4)[0]
    max_records = (len(data) - HEADER_SIZE) // RECORD_SIZE
    if count > max_records:
        count = max_records
    if count < 0:
        count = 0

    time_step = 0.1
    if lap_duration_ms > 0 and count > 0:
        time_step = (lap_duration_ms / 1000.0) / count

    points: List[TelemetryPoint] = []
    for i in range(count):
        off = HEADER_SIZE + i * RECORD_SIZE
        if off + RECORD_SIZE > len(data):
            break  # truncated file: keep complete records only

        lat, lon = struct.unpack_from("<dd", data, off)
        speed_mph = struct.unpack_from("<f", data, off + 16)[0]
        track_usage, altitude, accel_long, accel_lat, accel_z, gyro_x, gyro_y, gyro_z = struct.unpack_from(
            "<ffffffff", data, off + 28
        )

        points.append(
            TelemetryPoint(
                time_offset=float(i) * time_step,
                lat=lat,
                lon=lon,
                speed_mph=float(speed_mph),
                track_usage=float(track_usage) * 100.0,
                altitude=float(altitude),
                accel_long=float(accel_long) / 9.81,
                accel_lat=float(accel_lat) / 9.81,
                accel_z=float(accel_z) / 9.81,
                gyro_x=float(gyro_x),
                gyro_y=float(gyro_y),
                gyro_z=float(gyro_z),
            )
        )

    return points
