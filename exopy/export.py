"""Package export writes a session's laps and telemetry to CSV."""

import csv
from dataclasses import dataclass
from enum import Enum
from typing import List, TextIO

from exopy import catalyst, telemetry


class SpeedUnit(str, Enum):
    METERS_PER_SECOND = "m/s"
    MILES_PER_HOUR = "mph"
    KM_PER_HOUR = "kph"

    def convert(self, mph: float) -> float:
        if self == SpeedUnit.METERS_PER_SECOND:
            return mph * 0.44704
        elif self == SpeedUnit.KM_PER_HOUR:
            return mph * 1.60934
        else:
            return mph


def parse_speed_unit(s: str) -> SpeedUnit:
    for u in SpeedUnit:
        if u.value == s:
            return u
    raise ValueError(f"invalid speed unit \"{s}\" (want m/s, mph, or kph)")


@dataclass
class Stats:
    laps: int = 0
    rows: int = 0
    skipped: int = 0


def session_csv(
    w: TextIO,
    b: catalyst.Bundle,
    laps: List[catalyst.Lap],
    unit: SpeedUnit,
) -> Stats:
    cw = csv.writer(w, lineterminator="\n")
    header = [
        "Lap",
        "Time",
        "Lap Time",
        "Latitude",
        "Longitude",
        f"Speed ({unit.value})",
        "Accel Long (G)",
        "Accel Lat (G)",
        "Accel Z (G)",
        "Gyro X (rad/s)",
        "Gyro Y (rad/s)",
        "Gyro Z (rad/s)",
        "Track Usage (%)",
        "Altitude (m)",
    ]
    cw.writerow(header)

    stats = Stats()
    for lap in laps:
        if not lap.interp_loc:
            stats.skipped += 1
            continue
        try:
            path = b.lap_data_path(lap.interp_loc)
            points = telemetry.parse_lap_file(path, lap.lap_duration_ms)
        except Exception:
            stats.skipped += 1
            continue

        lap_start_s = lap.lap_start_time_ms / 1000.0
        for p in points:
            session_time = lap_start_s + p.time_offset
            row = [
                str(lap.lap_num),
                f"{session_time:.3f}",
                f"{p.time_offset:.3f}",
                f"{p.lat:.7f}",
                f"{p.lon:.7f}",
                f"{unit.convert(p.speed_mph):.3f}",
                f"{p.accel_long:.3f}",
                f"{p.accel_lat:.3f}",
                f"{p.accel_z:.3f}",
                f"{p.gyro_x:.4f}",
                f"{p.gyro_y:.4f}",
                f"{p.gyro_z:.4f}",
                f"{p.track_usage:.1f}",
                f"{p.altitude:.1f}",
            ]
            cw.writerow(row)
            stats.rows += 1
        stats.laps += 1

    return stats
