"""Offline regression tests. All simulated transfers use disposable Linux folders."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import channel_page
import sync
from executive_page import PAGE, bounding_errors
from project import (
    DATA, MODEL, PBIP, REPORT, ROOT, build, dump, load, report_files, validate, validate_bundle,
    validate_model_bindings,
)


class FoundationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.destination = self.base / "P003_PowerBI"
        self.state = self.base / "state"
        self.state.mkdir()

    def run_sync(self, command):
        sync.run(self.destination, self.state, ROOT, command)

    def test_pbip_and_data(self):
        self.assertEqual(validate(), 29)

    def test_refuses_modified_csv(self):
        folder = self.base / DATA
        shutil.copytree(ROOT / DATA, folder)
        with (folder / "executive_baseline.csv").open("a") as handle:
            handle.write("invalid")
        with self.assertRaisesRegex(ValueError, "CSV hash mismatch"):
            validate_bundle(folder)

    def test_sync_rerun_and_rollback_preserve_desktop_cache(self):
        self.run_sync("plan")
        self.assertFalse(self.destination.exists())
        self.run_sync("sync")
        first = sync.state_at(self.state)
        cache = self.destination / MODEL / ".pbi" / "cache.abf"
        cache.parent.mkdir()
        cache.write_text("disposable")
        self.run_sync("sync")
        self.assertEqual(sync.state_at(self.state), first)
        self.run_sync("rollback")
        self.assertEqual(sync.inventory(self.destination), {})
        self.assertEqual(cache.read_text(), "disposable")

    def test_refuses_drift_and_corrupt_backup(self):
        self.destination.mkdir()
        alien = self.destination / "existing.pbip"
        alien.write_text("existing")
        with self.assertRaisesRegex(ValueError, "Destination drift"):
            self.run_sync("sync")
        alien.unlink()
        self.run_sync("sync")
        entry = self.destination / PBIP
        original = entry.read_bytes()
        entry.write_text("Desktop edit")
        with self.assertRaisesRegex(ValueError, "Destination drift"):
            self.run_sync("rollback")
        self.assertEqual(entry.read_text(), "Desktop edit")
        entry.write_bytes(original)
        backup = self.state / sync.state_at(self.state)["backup"] / "files"
        (backup / "alien").write_text("corrupt backup")
        with self.assertRaisesRegex(ValueError, "drift"):
            self.run_sync("rollback")
        self.assertEqual(entry.read_bytes(), original)

    def test_refuses_unapplied_desktop_query_changes(self):
        self.run_sync("sync")
        pending = self.destination / MODEL / ".pbi" / "unappliedChanges.json"
        pending.parent.mkdir()
        pending.write_text("{}")
        with self.assertRaisesRegex(ValueError, "unapplied Power Query"):
            self.run_sync("sync")
        self.assertTrue(pending.exists())

    def test_static_validator_refuses_wrong_m_type(self):
        copy = self.base / "copy"
        sync.managed_source(ROOT, copy)
        spec = validate_bundle(copy / DATA)
        table = copy / MODEL / "definition/tables/executive_baseline.tmdl"
        table.write_text(table.read_text().replace("Int64.Type", "type number", 1))
        with self.assertRaisesRegex(ValueError, "M type bindings"):
            validate_model_bindings(copy, spec)

    def test_task007_upgrade_is_reproducible_and_rejects_visual_drift(self):
        working = self.base / "working"
        working.mkdir()
        page = f"{REPORT}/definition/pages/{PAGE}/page.json"
        (working / page).parent.mkdir(parents=True)
        (working / page).write_text(dump(report_files()[page]))
        build(working)
        first = sync.inventory(working)
        self.assertEqual(validate(working), 29)
        build(working)
        self.assertEqual(sync.inventory(working), first)
        visual = next((working / page).parent.glob("visuals/*/visual.json"))
        visual.write_text(visual.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "Existing definition differs"):
            build(working)
        self.assertEqual(visual.read_text().count("\n"), (ROOT / visual.relative_to(working)).read_text().count("\n") + 1)

    def test_executive_upgrade_and_rollback_to_accepted_foundation(self):
        sync.managed_source(ROOT, self.destination)
        folder = self.destination / REPORT / "definition"
        page = folder / "pages" / PAGE / "page.json"
        shutil.rmtree(page.parent / "visuals")
        shutil.rmtree(folder / "pages" / channel_page.PAGE)
        metadata = f"{REPORT}/definition/pages/pages.json"
        (self.destination / metadata).write_text(dump(report_files()[metadata]))
        (folder / "reportExtensions.json").unlink()
        page.write_text(dump(report_files()[page.relative_to(self.destination).as_posix()]))
        before = sync.inventory(self.destination)
        sync.atomic_json(self.state / "current.json", {"files": before, "backup": None})
        self.run_sync("sync")
        after = sync.inventory(self.destination)
        changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
        self.assertEqual(len(changed), 24)
        self.assertTrue(all(name.startswith(f"{REPORT}/definition/") for name in changed))
        self.assertEqual(validate(self.destination), 29)
        self.run_sync("rollback")
        self.assertEqual(sync.inventory(self.destination), before)

    def test_bounding_checks_reject_overlap_and_out_of_canvas(self):
        folder = ROOT / REPORT / "definition" / "pages" / PAGE
        docs = [load(path) for path in (folder / "visuals").glob("*/visual.json")]
        page = load(folder / "page.json")
        self.assertEqual(bounding_errors(page, docs), [])
        docs[1]["position"].update(docs[0]["position"])
        self.assertTrue(any("overlap" in item for item in bounding_errors(page, docs)))
        docs[1]["position"]["y"] = 1080
        self.assertTrue(any("Out of canvas" in item for item in bounding_errors(page, docs)))

    def test_recovers_partial_interrupted_copy(self):
        real_apply = sync.apply

        def interrupted(destination, payload, before, after):
            key = next(iter(after))
            real_apply(destination, payload, before, {key: after[key]})
            raise SystemExit("simulated process interruption")

        with patch.object(sync, "apply", side_effect=interrupted):
            with self.assertRaisesRegex(SystemExit, "interruption"):
                self.run_sync("sync")
        self.assertTrue((self.state / "pending.json").is_file())
        with self.assertRaisesRegex(ValueError, "Interrupted operation"):
            self.run_sync("sync")
        self.run_sync("recover")
        self.assertEqual(sync.inventory(self.destination), {})
        self.assertFalse((self.state / "pending.json").exists())


if __name__ == "__main__":
    unittest.main()
