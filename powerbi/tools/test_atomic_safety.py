"""Fault injection for P003 writes and recovery in disposable directories."""
import errno
import hashlib
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import atomic_io
import project
import sync
from executive_page import PAGE


class AtomicSafetyTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.target = self.root / "definition.json"
        self.target.write_bytes(b"approved")
        self.target.chmod(0o640)

    def write(self, contents=b"replacement"):
        with atomic_io.staging_area(self.root, ".test-stage") as stage:
            atomic_io.atomic_write(self.target, contents, expected=b"approved", stage=stage)

    def assert_approved(self):
        self.assertEqual(self.target.read_bytes(), b"approved")
        self.assertEqual(set(self.root.iterdir()), {self.target})

    def test_before_staging(self):
        with patch.object(atomic_io.tempfile, "NamedTemporaryFile", side_effect=OSError("stage failed")):
            with self.assertRaisesRegex(OSError, "stage failed"):
                self.write()
        self.assert_approved()

    def test_partial_stage_write(self):
        original = tempfile.NamedTemporaryFile

        def create_partial_stage(*args, **kwargs):
            handle = original(*args, **kwargs)
            write = handle.write

            def interrupted(contents):
                write(contents[:3])
                raise OSError(errno.ENOSPC, "simulated full disk")

            handle.write = interrupted
            return handle

        with patch.object(atomic_io.tempfile, "NamedTemporaryFile", side_effect=create_partial_stage):
            with self.assertRaisesRegex(OSError, "simulated full disk"):
                self.write()
        self.assert_approved()

    def test_before_replacement(self):
        with patch.object(atomic_io.os, "replace", side_effect=OSError("replacement failed")):
            with self.assertRaisesRegex(OSError, "replacement failed"):
                self.write()
        self.assert_approved()

    def test_corrupted_stage_refused(self):
        read = Path.read_bytes

        def corrupt(path):
            contents = read(path)
            return contents[:-1] if path.name.startswith("p003-write-") else contents

        with patch.object(Path, "read_bytes", corrupt):
            with self.assertRaisesRegex(OSError, "Staged content verification failed"):
                self.write()
        self.assert_approved()

    def test_after_replacement(self):
        with patch.object(atomic_io, "fsync_directory", side_effect=OSError("directory sync failed")):
            with self.assertRaisesRegex(OSError, "directory sync failed"):
                self.write()
        self.assertEqual(self.target.read_bytes(), b"replacement")
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
        self.assertEqual(set(self.root.iterdir()), {self.target})
        with atomic_io.staging_area(self.root, ".test-stage") as stage:
            with patch.object(atomic_io.tempfile, "NamedTemporaryFile", side_effect=AssertionError):
                atomic_io.atomic_write(self.target, b"replacement", expected=b"replacement", stage=stage)

    def test_identical_file_and_stale_scratch(self):
        stage = self.root / ".test-stage"
        stage.mkdir(mode=0o700)
        (stage / "p003-write-abandoned").write_bytes(b"partial")
        original = self.target.stat()
        self.write(b"approved")
        self.assert_approved()
        current = self.target.stat()
        self.assertEqual((current.st_ino, current.st_mtime_ns), (original.st_ino, original.st_mtime_ns))

    def test_refuses_symlinks_and_unknown_scratch(self):
        link = self.root / "link.json"
        link.symlink_to(self.target)
        with atomic_io.staging_area(self.root, ".test-stage") as stage:
            with self.assertRaisesRegex(ValueError, "Symlink refused"):
                atomic_io.atomic_write(link, b"replacement", expected=b"approved", stage=stage)
        stage.mkdir()
        (stage / "p003-write-hardlink").hardlink_to(self.target)
        with self.assertRaisesRegex(ValueError, "Unexpected staging entry"):
            self.write()
        self.assertEqual(self.target.read_bytes(), b"approved")
        self.assertTrue((stage / "p003-write-hardlink").exists())


class PipelineInterruptionTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        self.destination = self.root / "destination"

    def test_partial_build_reruns_and_refuses_drift(self):
        working = self.root / "working"
        working.mkdir()
        bundle = self.root / "pinned-copy"
        shutil.copytree(project.ROOT / project.DATA, bundle)
        relative = f"{project.REPORT}/definition/pages/{PAGE}/page.json"
        page = working / relative
        page.parent.mkdir(parents=True)
        old = project.dump(project.report_files()[relative]).encode("utf-8")
        page.write_bytes(old)
        # Emulate a previous hard stop during private data staging.
        csv_stage = working / ".p003-csv-stage"
        csv_stage.mkdir(mode=0o700)
        (csv_stage / "manifest.json").write_bytes(b"partial")
        replace = os.replace

        def interrupt_page(source, destination):
            if destination == page:
                raise OSError("page replacement interrupted")
            replace(source, destination)

        with patch.object(project, "SOURCE_BUNDLE", bundle):
            with patch.object(atomic_io.os, "replace", side_effect=interrupt_page):
                with self.assertRaisesRegex(OSError, "page replacement interrupted"):
                    project.build(working)
            self.assertEqual(page.read_bytes(), old)
            self.assertTrue((working / project.PBIP).is_file())
            self.assertTrue(all(path.stat().st_size for path in project.files_under(working)))
            project.build(working)
            self.assertEqual(project.validate(working), 29)
            expected = {name: (project.ROOT / name).read_bytes()
                        for name in project.definition_files(project.validate_bundle(bundle))}
            before = {name: (working / name).stat().st_ino for name in expected}
            project.build(working)
            self.assertEqual({name: (working / name).read_bytes() for name in expected}, expected)
            self.assertEqual({name: (working / name).stat().st_ino for name in expected}, before)
            self.assertFalse(csv_stage.exists())
            page.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "Existing definition differs"):
                project.build(working)
            self.assertEqual(page.read_bytes(), b"")

    def test_interrupted_upgrade_recovers_and_preserves_approved_files(self):
        source = self.root / "source"
        sync.managed_source(project.ROOT, source)
        sync.managed_source(source, self.destination)
        page = self.destination / project.REPORT / "definition" / "pages" / PAGE / "page.json"
        relative = page.relative_to(self.destination).as_posix()
        page.write_text(project.dump(project.report_files()[relative]), encoding="utf-8")
        before = sync.inventory(self.destination)
        sync.atomic_json(self.state / "current.json", {"files": before, "backup": None})
        replace = os.replace

        def interrupt_after_page(scratch, destination):
            replace(scratch, destination)
            if destination == page:
                raise SystemExit("simulated abrupt interruption after replacement")

        with patch.object(atomic_io.os, "replace", side_effect=interrupt_after_page):
            with self.assertRaisesRegex(SystemExit, "abrupt interruption"):
                sync.run(self.destination, self.state, source, "sync")
        self.assertTrue((self.state / "pending.json").is_file())
        self.assertEqual(page.read_bytes(), (source / relative).read_bytes())
        self.assertTrue(all(path.stat().st_size for path in project.files_under(self.destination)))
        with self.assertRaisesRegex(ValueError, "Interrupted operation recorded"):
            sync.run(self.destination, self.state, source, "sync")
        # Foreign edits must survive a refused recovery.
        pbip = self.destination / project.PBIP
        original = pbip.read_bytes()
        pbip.write_bytes(b"foreign edit")
        with self.assertRaisesRegex(ValueError, "unrecognized changes"):
            sync.run(self.destination, self.state, source, "recover")
        self.assertEqual(pbip.read_bytes(), b"foreign edit")
        pbip.write_bytes(original)
        sync.run(self.destination, self.state, source, "recover")
        self.assertEqual(sync.inventory(self.destination), before)
        sync.run(self.destination, self.state, source, "sync")
        self.assertEqual(project.validate(self.destination, private=False), 29)
        sync.run(self.destination, self.state, source, "rollback")
        self.assertEqual(sync.inventory(self.destination), before)

    def test_transfer_rejects_traversal_and_desktop_cache_entries(self):
        ancestor = self.root / "approved.txt"
        ancestor.write_bytes(b"approved")
        fingerprint = hashlib.sha256(b"approved").hexdigest()
        for path in ("../approved.txt", f"{project.MODEL}/.pbi/cache.abf",
                     f"{project.REPORT}/../../approved.txt", f"{project.REPORT}/file.json:stream",
                     f"{project.MODEL}/.PBI/cache.abf", "C:\\approved.txt"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Invalid managed inventory"):
                sync.apply(self.destination, self.root, {path: fingerprint}, {})
        self.assertEqual(ancestor.read_bytes(), b"approved")
