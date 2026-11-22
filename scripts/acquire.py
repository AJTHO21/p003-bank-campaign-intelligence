"""Download the UCI archive and install an immutable source snapshot."""
import csv
import io
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from profile_data import read_rows, verify_snapshot
from source import ARCHIVE, CSV, INNER, MANIFEST, RAW, README, URL, digest


def member_bytes(archive, filename):
    matches = [item for item in archive.infolist()
               if not item.is_dir() and PurePosixPath(item.filename).name == filename]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one archive member named {filename}")
    return archive.read(matches[0]), matches[0].filename


def acquire():
    if RAW.exists():
        verify_snapshot(RAW)
        print(f"Verified existing snapshot at {RAW}")
        return
    with tempfile.TemporaryDirectory(dir=RAW.parent, prefix=".acquire-") as temp:
        snapshot = Path(temp) / "snapshot"
        snapshot.mkdir()
        archive_path = snapshot / ARCHIVE
        subprocess.run(
            ["curl", "--fail", "--silent", "--show-error", "--location",
             "--proto", "=https", "--proto-redir", "=https", "--max-time", "120",
             "--output", str(archive_path), URL],
            check=True,
        )
        acquired_at = datetime.now(timezone.utc).isoformat()
        with ZipFile(archive_path) as archive:
            inner_bytes, archive_member = member_bytes(archive, INNER)
        (snapshot / INNER).write_bytes(inner_bytes)
        with ZipFile(io.BytesIO(inner_bytes)) as archive:
            csv_bytes, csv_member = member_bytes(archive, CSV)
            readme_bytes, readme_member = member_bytes(archive, README)
        (snapshot / CSV).write_bytes(csv_bytes)
        (snapshot / README).write_bytes(readme_bytes)
        read_rows(snapshot / CSV)
        manifest = {
            "acquired_at_utc": acquired_at,
            "source_url": URL,
            "catalog_url": "https://archive.ics.uci.edu/dataset/222/bank+marketing",
            "citation": "Moro, S., Rita, P., & Cortez, P. (2014). Bank Marketing [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5K306",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "version": "UCI 222, full bank-additional variant; identified by CSV SHA-256",
            "archive_member": archive_member,
            "selected_member": csv_member,
            "documentation_member": readme_member,
            "files": {
                name: {"bytes": (snapshot / name).stat().st_size,
                       "sha256": digest(snapshot / name)}
                for name in (ARCHIVE, INNER, CSV, README)
            },
        }
        (snapshot / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
        for path in snapshot.iterdir():
            path.chmod(0o444)
        try:
            snapshot.rename(RAW)
        except OSError:
            if not RAW.is_dir():
                raise
            verify_snapshot(RAW)
        else:
            RAW.chmod(0o555)
    print(f"Verified source snapshot at {RAW}")


if __name__ == "__main__":
    try:
        acquire()
    except (OSError, ValueError, KeyError, BadZipFile, csv.Error, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Acquisition failed: {error}")
