"""Command exopy is a local CLI for Catalyst SupportLogs."""

import argparse
import datetime
import os
import sys
import tempfile
from typing import List, Optional

from exopy import archive, catalyst, export

DEFAULT_PASSPHRASE = "FF59E1881B4ED01C5C2F5F01890AFF25E9764D27"
PASSPHRASE_ENV = "EXOPY_GPG_PASSPHRASE"


def get_passphrase(flag_val: Optional[str]) -> str:
    if flag_val:
        return flag_val
    return os.environ.get(PASSPHRASE_ENV, DEFAULT_PASSPHRASE)


def resolve_bundle(path: str, pass_flag: Optional[str]):
    """resolve_bundle opens path as an extracted bundle, or auto-extracts an archive to a temp dir."""
    if os.path.exists(path) and os.path.isdir(path):
        try:
            b = catalyst.open_bundle(path)
            return b, lambda: None
        except Exception:
            pass

    parts = archive.collect_parts(path)
    tmp_dir = tempfile.mkdtemp(prefix="exopy-")

    def cleanup():
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)

    sys.stderr.write(f"Decrypting and extracting {len(parts)} part(s) to a temp dir...\n")
    try:
        res = archive.extract(parts, get_passphrase(pass_flag), tmp_dir)
    except Exception:
        cleanup()
        raise

    if res.partial_recovery:
        sys.stderr.write(f"warning: partial recovery — {res.notes}\n")

    try:
        b = catalyst.open_bundle(tmp_dir)
    except Exception:
        cleanup()
        raise

    return b, cleanup


def cmd_extract(args: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="exopy extract", description="Decrypt & unpack an upload"
    )
    parser.add_argument("input", help="Input path")
    parser.add_argument("-o", "--out", required=True, dest="out", help="output directory")
    parser.add_argument("--passphrase", default="", help="GPG passphrase")

    parsed = parser.parse_args(args)

    parts = archive.collect_parts(parsed.input)
    sys.stderr.write(f"Decrypting and extracting {len(parts)} part(s)...\n")
    res = archive.extract(parts, get_passphrase(parsed.passphrase), parsed.out)
    if res.partial_recovery:
        sys.stderr.write(f"warning: partial recovery — {res.notes}\n")
    print(f"Extracted {res.files} files to {parsed.out}")
    return 0


def format_lap_time(ms: Optional[int]) -> str:
    if ms is None or ms <= 0:
        return "-"
    minutes = ms // 60000
    sec = (ms % 60000) / 1000.0
    return f"{minutes}:{sec:06.3f}"


def format_top_speed(mps: Optional[float]) -> str:
    if mps is None:
        return "-"
    kph = mps * 3.6
    return f"{kph:.1f} km/h"


def format_car(make: Optional[str], model: Optional[str]) -> str:
    if make and model:
        return f"{make} {model}"
    if make:
        return make
    if model:
        return model
    return "-"


def cmd_sessions(args: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="exopy sessions", description="List sessions in a bundle"
    )
    parser.add_argument("path", help="Path to extracted bundle or archive")
    parser.add_argument("--passphrase", default="", help="GPG passphrase")

    parsed = parser.parse_args(args)

    b, cleanup = resolve_bundle(parsed.path, parsed.passphrase)
    try:
        sessions = b.list_sessions()
        if not sessions:
            print("No sessions found.")
            return 0

        rows = []
        header = ["ID", "DATE", "TRACK", "CAR", "LAPS", "BEST LAP", "TOP SPEED"]
        rows.append(header)

        for s in sessions:
            date_str = (
                datetime.datetime.fromtimestamp(
                    s.start_time_utc_s, tz=datetime.timezone.utc
                ).strftime("%Y-%m-%d %H:%M")
                if s.start_time_utc_s
                else "-"
            )
            rows.append([
                str(s.id),
                date_str,
                s.track_name or "-",
                format_car(s.make, s.model),
                str(s.num_laps) if s.num_laps is not None else "-",
                format_lap_time(s.fastest_lap_time_ms),
                format_top_speed(s.max_speed_mps),
            ])

        col_widths = [
            max(len(row[col]) for row in rows) for col in range(len(header))
        ]

        for row in rows:
            line = "  ".join(val.ljust(col_widths[i]) for i, val in enumerate(row)).rstrip()
            print(line)

        return 0
    finally:
        b.close()
        cleanup()


def cmd_export(args: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="exopy export", description="Export a session's telemetry to CSV"
    )
    parser.add_argument("path", help="Path to extracted bundle or archive")
    parser.add_argument("--session", required=True, help="session ID to export (required)")
    parser.add_argument("-o", "--out", default="", help="output CSV file (default: stdout)")
    parser.add_argument("--speed", default="m/s", help="speed unit: m/s, mph, or kph")
    parser.add_argument("--passphrase", default="", help="GPG passphrase")

    parsed = parser.parse_args(args)

    unit = export.parse_speed_unit(parsed.speed)

    b, cleanup = resolve_bundle(parsed.path, parsed.passphrase)
    try:
        b.get_session(parsed.session)
        laps = b.laps(parsed.session)
        if not laps:
            raise ValueError(f"session {parsed.session} has no laps")

        out_file = parsed.out
        if out_file:
            f = open(out_file, "w", encoding="utf-8")
        else:
            f = sys.stdout

        try:
            stats = export.session_csv(f, b, laps, unit)
        finally:
            if out_file != "":
                f.close()

        dest = out_file if out_file else "stdout"
        msg = f"Wrote {stats.rows} rows from {stats.laps} laps to {dest}"
        if stats.skipped > 0:
            msg += f" ({stats.skipped} laps skipped — no telemetry)"
        sys.stderr.write(msg + "\n")
        return 0
    finally:
        b.close()
        cleanup()


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        usage()
        return 2

    cmd = argv[0]
    if cmd in ("-h", "--help", "help"):
        usage()
        return 0

    try:
        if cmd == "extract":
            return cmd_extract(argv[1:])
        elif cmd == "sessions":
            return cmd_sessions(argv[1:])
        elif cmd == "export":
            return cmd_export(argv[1:])
        else:
            sys.stderr.write(f'unknown command "{cmd}"\n\n')
            usage()
            return 2
    except Exception as e:
        sys.stderr.write(f"error: {e}\n")
        return 1


def usage():
    sys.stderr.write(f"""exopy - Catalyst telemetry CLI

Usage:
  exopy extract  <input> -o <dir> [--passphrase P]   Decrypt & unpack an upload
  exopy sessions <path>          [--passphrase P]     List sessions in a bundle
  exopy export   <path> --session ID [-o file.csv] [--speed m/s|mph|kph] [--passphrase P]

<input> may be a directory of "*.gpg" parts, a single "...tar.gz.gpg", or one
split part ("...gpg.aa"). <path> may be an already-extracted directory or an
archive (auto-extracted to a temp dir).

The GPG passphrase defaults to the built-in Catalyst passphrase; override it with
--passphrase or the {PASSPHRASE_ENV} env var.
""")


if __name__ == "__main__":
    sys.exit(main())
