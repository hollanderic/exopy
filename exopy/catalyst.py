"""Package catalyst reads an extracted Catalyst bundle: catalyst.db SQLite metadata and binary lap telemetry files."""

import os
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional

DATA_FOLDERS = {
    "LapData",
    "Meanlines",
    "OptLapManifests",
    "RawAccel",
    "RawGNSS",
    "RawGyro",
    "RawLatPos",
    "VideoManifests",
}


@dataclass
class Session:
    id: int
    start_time_utc_s: int
    num_laps: Optional[int]
    fastest_lap_time_ms: Optional[int]
    max_speed_mps: Optional[float]
    session_duration_ms: Optional[int]
    track_name: Optional[str]
    make: Optional[str]
    model: Optional[str]


@dataclass
class Lap:
    id: int
    session_id: int
    lap_num: int
    lap_start_time_ms: int
    lap_duration_ms: int
    interp_loc: Optional[str]


class Bundle:

    def __init__(
        self,
        root: str,
        db_path: str,
        folder_dirs: Dict[str, str],
        files: Dict[str, str],
    ):
        self.root = root
        self.db_path = db_path
        self.folder_dirs = folder_dirs
        self.files = files
        self.conn: Optional[sqlite3.Connection] = None

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def list_sessions(self) -> List[Session]:
        return list_sessions(self)

    def get_session(self, session_id: str) -> Session:
        return get_session(self, session_id)

    def laps(self, session_id: str) -> List[Lap]:
        return laps(self, session_id)

    def lap_data_path(self, loc: str) -> str:
        return lap_data_path(self, loc)


SESSION_SELECT = """
	SELECT
		sr.id,
		sr.session_start_time_utc_s,
		sr.num_laps,
		sr.fastest_lap_time_ms,
		sr.max_speed_mps,
		sr.session_duration_ms,
		f.name  AS track_name,
		c.make  AS make,
		c.model AS model
	FROM session_results sr
	LEFT JOIN session_configuration sc ON sr.id = sc.id
	LEFT JOIN track_configurations  tc ON sc.track_config_id = tc.id
	LEFT JOIN track_routes          tr ON tc.track_route_id  = tr.id
	LEFT JOIN facilities            f  ON tr.facility_id      = f.id
	LEFT JOIN cars                  c  ON sc.car_id           = c.id
"""

FALLBACK_SELECT = """
	SELECT id, session_start_time_utc_s, num_laps, fastest_lap_time_ms,
	       max_speed_mps, session_duration_ms, NULL, NULL, NULL
	FROM session_results sr
"""


def open_bundle(root: str) -> Bundle:
    """Open locates catalyst.db under root and indexes the data folders."""
    db_path = ""
    folder_dirs: Dict[str, str] = {}
    files: Dict[str, str] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            if d in DATA_FOLDERS and d not in folder_dirs:
                folder_dirs[d] = os.path.join(dirpath, d)

        for f in filenames:
            if f == "catalyst.db" and not db_path:
                db_path = os.path.join(dirpath, f)
            if f not in files:
                files[f] = os.path.join(dirpath, f)

    if not db_path:
        raise ValueError(f"catalyst.db not found under {root}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    b = Bundle(root, db_path, folder_dirs, files)
    b.conn = conn
    return b


def _query_sessions(b: Bundle, clause: str, params: tuple = ()) -> List[Session]:
    assert b.conn is not None
    cursor = b.conn.cursor()
    try:
        cursor.execute(SESSION_SELECT + clause, params)
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        cursor.execute(FALLBACK_SELECT + clause, params)
        rows = cursor.fetchall()

    sessions: List[Session] = []
    for r in rows:
        sessions.append(
            Session(
                id=r[0],
                start_time_utc_s=r[1],
                num_laps=r[2],
                fastest_lap_time_ms=r[3],
                max_speed_mps=r[4],
                session_duration_ms=r[5],
                track_name=r[6],
                make=r[7],
                model=r[8],
            )
        )
    return sessions


def list_sessions(b: Bundle) -> List[Session]:
    """ListSessions returns all sessions, newest first."""
    return _query_sessions(b, " ORDER BY sr.session_start_time_utc_s DESC")


def get_session(b: Bundle, session_id: str) -> Session:
    """GetSession returns one session by id."""
    sessions = _query_sessions(b, " WHERE sr.id = ?", (session_id,))
    if not sessions:
        raise ValueError(f"session {session_id} not found")
    return sessions[0]


def laps(b: Bundle, session_id: str) -> List[Lap]:
    """Laps returns a session's laps ordered by lap number."""
    assert b.conn is not None
    cursor = b.conn.cursor()
    cursor.execute(
        """SELECT id, session_id, lap_num, lap_start_time_ms, lap_duration_ms, interp_lap_data_loc
		 FROM lap_data WHERE session_id = ? ORDER BY lap_num ASC""",
        (session_id,),
    )
    rows = cursor.fetchall()
    out: List[Lap] = []
    for r in rows:
        out.append(
            Lap(
                id=r[0],
                session_id=r[1],
                lap_num=r[2],
                lap_start_time_ms=r[3],
                lap_duration_ms=r[4],
                interp_loc=r[5],
            )
        )
    return out


def lap_data_path(b: Bundle, loc: str) -> str:
    """LapDataPath resolves a lap's stored interp_lap_data_loc to a local file."""
    loc = (loc or "").strip()
    if not loc:
        raise ValueError("empty lap data location")

    parts = loc.replace("\\", "/").split("/")
    file_name = parts[-1]
    folder = parts[-2] if len(parts) >= 2 else "LapData"

    check_dirs = [b.folder_dirs.get(folder), b.folder_dirs.get("LapData")]
    for d in check_dirs:
        if d:
            p = os.path.join(d, file_name)
            if os.path.isfile(p):
                return p

    if file_name in b.files:
        return b.files[file_name]

    raise ValueError(f"lap data file '{file_name}' not found under {b.root}")
