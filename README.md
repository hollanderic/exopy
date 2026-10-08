# exopy (Python port of exotherm-go)

This is a port of [exotherm-go](https://github.com/Friss/exotherm-go) to Python.  It was ported using Gemini and all credit and appreciation given to Friss for the original implementation and for creating exotherm-go.

A command-line tool for reading [Garmin Catalyst v1](https://www.garmin.com/en-US/p/690726/) data logger SupportLogs on your machine, rewritten in Python.

It can:
- **extract** the GPG-encrypted, gzipped tar archive a Catalyst logger produces,
- **list** the sessions inside it, and
- **export** a session's telemetry to CSV.

## Requirements & Installation

Python 3.9+ is required.

```bash
cd py
pip install -r requirements.txt
pip install -e .
```

## Usage

```bash
# Extract archive
exotherm extract ./upload -o ./extracted

# List sessions
exotherm sessions ./extracted

# Export session telemetry to CSV
exotherm export ./extracted --session 145 -o session145.csv
exotherm export ./extracted --session 145 --speed kph -o session145.csv
```

Alternatively, run without installation using `python -m exotherm`:

```bash
python -m exotherm sessions ../testdata/demo
```

## Running Tests

```bash
pytest
```
