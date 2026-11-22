"""Explicit, guarded P003 Windows sync and recovery. Default action is a read-only plan."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from atomic_io import atomic_write, check_path, fsync_directory, mkdir_durable, read_existing, staging_area
from project import ROOT, DATA, MODEL, PBIP, REPORT, digest, dump, files_under, require, validate

STATE = ROOT / ".sync"
EMPTY = {"files": {}, "backup": None}


def inventory(root):
    return {file.relative_to(root).as_posix(): digest(file) for file in files_under(root)}


def atomic_json(path, document):
    with staging_area(path.parent, ".p003-state-stage") as stage:
        atomic_write(path, dump(document).encode("utf-8"), expected=read_existing(path),
                     stage=stage, mode=0o600)


def read_state(path):
    contents = read_existing(path)
    return json.loads(contents) if contents is not None else None


def check_inventory(files):
    require(isinstance(files, dict), "Invalid managed inventory")
    for relative, fingerprint in files.items():
        path = Path(relative)
        require(path.as_posix() == relative and not path.is_absolute()
                and "\\" not in relative and ":" not in relative
                and all(part.lower() not in {"..", ".pbi"} and part == part.rstrip(" .")
                        for part in path.parts)
                and (relative == PBIP or (len(path.parts) > 1 and path.parts[0] in (REPORT, MODEL, DATA)))
                and isinstance(fingerprint, str) and re.fullmatch("[0-9a-f]{64}", fingerprint),
                f"Invalid managed inventory entry: {relative}")


def checked_state(document):
    require(isinstance(document, dict) and set(document) == {"files", "backup"},
            "Invalid sync state")
    check_inventory(document["files"])
    return document


def state_at(state):
    path = state / "current.json"
    document = read_state(path)
    return EMPTY if document is None and not path.exists() else checked_state(document)


def require_matching(actual, expected):
    differences = [key for key in sorted(actual.keys() | expected.keys()) if actual.get(key) != expected.get(key)]
    require(not differences, "Destination drift or unmanaged files: " + ", ".join(differences))


def copy_verified(source, output, fingerprint, stage):
    contents = read_existing(source)
    require(contents is not None and hashlib.sha256(contents).hexdigest() == fingerprint,
            f"Invalid transfer payload: {source}")
    mkdir_durable(output.parent)
    atomic_write(output, contents, expected=None, stage=stage, mode=0o600)


def managed_source(source, staged):
    mkdir_durable(staged, mode=0o700)
    mkdir_durable(staged / DATA, mode=0o700)
    with staging_area(staged, ".p003-copy-stage") as stage:
        for relative in (PBIP, REPORT, MODEL, DATA):
            path = source / relative
            check_path(path)
            paths = [path] if relative == PBIP else files_under(path)
            for file in paths:
                copy_verified(file, staged / file.relative_to(source), digest(file), stage)


def snapshot(source, backup, expected):
    mkdir_durable(backup, mode=0o700)
    with staging_area(backup, ".p003-copy-stage") as stage:
        for relative, fingerprint in expected.items():
            copy_verified(source / relative, backup / relative, fingerprint, stage)
    require_matching(inventory(backup), expected)


def compatible(current, before, after):
    return all(current.get(key) in (before.get(key), after.get(key))
               for key in current.keys() | before.keys() | after.keys())


def apply(destination, payload, before, after):
    check_inventory(before)
    check_inventory(after)
    with staging_area(destination.parent, ".P003-transfer-stage") as stage:
        for relative in sorted(before.keys() | after.keys()):
            if before.get(relative) == after.get(relative):
                continue
            target = destination / relative
            original = read_existing(target)
            fingerprint = hashlib.sha256(original).hexdigest() if original is not None else None
            require(fingerprint == before.get(relative), f"Destination changed during transfer: {relative}")
            if relative in after:
                contents = read_existing(payload / relative)
                require(contents is not None and hashlib.sha256(contents).hexdigest() == after[relative],
                        f"Invalid transfer payload: {relative}")
                mkdir_durable(target.parent)
                atomic_write(target, contents, expected=original, stage=stage, mode=0o600)
            else:
                require(read_existing(target) == original, f"Destination changed during transfer: {relative}")
                target.unlink()
                fsync_directory(target.parent)


def backup_directory(state, name):
    require(isinstance(name, str) and re.fullmatch(r"backup-[a-zA-Z0-9_-]+", name),
            "Invalid backup reference")
    path = state / name
    check_path(path)
    require(path.is_dir(), "Invalid backup reference")
    return path


def recover(destination, state):
    journal = state / "pending.json"
    pending = read_state(journal)
    require(isinstance(pending, dict) and set(pending) == {"before", "after", "operation_backup"},
            "Missing or invalid interrupted operation journal")
    backup = backup_directory(state, pending["operation_backup"])
    before = checked_state(pending["before"])
    after = checked_state(pending["after"])
    current = inventory(destination)
    require(compatible(current, before["files"], after["files"]),
            f"Destination has unrecognized changes. Inspect the backup at {backup}")
    require_matching(inventory(backup / "files"), before["files"])
    apply(destination, backup / "files", current, before["files"])
    require_matching(inventory(destination), before["files"])
    atomic_json(state / "current.json", before)
    journal.unlink()
    fsync_directory(state)
    print(f"Recovered the pre-operation state using {backup}")


def run(destination, state, source, command):
    require(command in {"plan", "sync", "rollback", "recover"}, "Invalid sync command")
    check_path(state)
    require(destination.parent.is_dir(), "Destination parent does not exist")
    require(destination.resolve() == destination, "Noncanonical or symlinked destination")
    pending = state / "pending.json"
    if command == "recover":
        recover(destination, state)
        return
    check_path(pending)
    require(not pending.exists(), "Interrupted operation recorded. Run recover after reviewing the backup.")
    before = state_at(state)
    require_matching(inventory(destination), before["files"])
    require(not (destination / MODEL / ".pbi" / "unappliedChanges.json").exists(),
            "Desktop has unapplied Power Query changes. Reconcile them before transfer.")
    if command == "plan":
        validate(source)
        print(f"{destination}: {len(before['files'])} current managed files. Source validation passed.")
        return

    with tempfile.TemporaryDirectory(dir=state) as work:
        if command == "sync":
            payload = Path(work)
            managed_source(source, payload)
            validate(payload)
            desired = inventory(payload)
            if desired == before["files"]:
                print("Destination already matches the verified P003 source.")
                return
            require(before["files"].keys() <= desired.keys(), "Sync would remove managed files; reconcile first")
            after = {"files": desired, "backup": None}
        else:
            require(before["backup"] is not None, "There is no successful sync to roll back")
            previous_backup = backup_directory(state, before["backup"])
            after = checked_state(read_state(previous_backup / "previous.json"))
            payload = previous_backup / "files"
            require_matching(inventory(payload), after["files"])
        backup = Path(tempfile.mkdtemp(prefix="backup-", dir=state))
        fsync_directory(state)
        snapshot(destination, backup / "files", before["files"])
        atomic_json(backup / "previous.json", before)
        require_matching(inventory(destination), before["files"])
        if command == "sync":
            after["backup"] = backup.name
        atomic_json(pending, {"before": before, "after": after, "operation_backup": backup.name})
        print(f"Verified pre-operation backup: {backup}", flush=True)
        try:
            apply(destination, payload, before["files"], after["files"])
            require_matching(inventory(destination), after["files"])
            if command == "sync":
                validate(destination, private=False)
            atomic_json(state / "current.json", after)
        except (Exception, KeyboardInterrupt):
            recover(destination, state)
            raise
        pending.unlink()
        fsync_directory(state)
        print(f"{command.capitalize()} verified at {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "sync", "rollback", "recover"), nargs="?", default="plan")
    parser.add_argument("--destination", type=Path, required=True,
                        help="Absolute destination as seen from WSL")
    parser.add_argument("--desktop-closed", action="store_true")
    args = parser.parse_args()
    destination = args.destination
    require(destination.is_absolute() and destination.resolve() == destination,
            "Destination must be an absolute, canonical path")
    require(not destination.is_relative_to(ROOT.parent) and not ROOT.parent.is_relative_to(destination),
            "Destination must be separate from the source checkout")
    state = STATE / hashlib.sha256(os.fsencode(destination)).hexdigest()
    if args.command == "plan":
        run(destination, state, ROOT, args.command)
        return
    require(args.desktop_closed, "Close Power BI Desktop and pass --desktop-closed")
    mkdir_durable(STATE, mode=0o700)
    mkdir_durable(state, mode=0o700)
    for folder in (STATE, state):
        require(folder.stat().st_mode & 0o077 == 0, "Backup state directory must be private")
    with os.fdopen(os.open(state / "lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600),
                   "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(destination, state, ROOT, args.command)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(f"Stopped: {error}")
