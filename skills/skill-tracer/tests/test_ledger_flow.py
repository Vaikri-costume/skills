"""begin-round / close-round gate / fill-address / stale-PENDING supersession / legacy in-flight marker (scripts/append_ledger.py, scripts/ledger_cascade.py, scripts/ledger_common.py). Run: python3 -m unittest discover -s tests   (from the skill root), or
python3 tests/test_ledger_flow.py."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import ledger_common as lc  # noqa: E402


def run(script, *args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], input=stdin,
                          capture_output=True, text=True)


class LedgerFlow(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.led = str(Path(self._tmp.name) / "t.md")
        self.tgt = str(Path(self._tmp.name).resolve())

    def tearDown(self):
        self._tmp.cleanup()

    def test_begin_round_creates_ledger_marker_and_options(self):
        r = run("append_ledger.py", "begin-round", self.led, "--round", "1", "--runtime", "2026-10-05T10:00", "--target", self.tgt,
                "--set", "rounds-budget=2")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self.led).read_text()
        self.assertIn("in-flight:: 2026-10-05T10:00 prepass running round-1", text)
        self.assertEqual(lc.parse_run_options(text)["rounds-budget"], "2")
        again = json.loads(run("append_ledger.py", "begin-round", self.led, "--round", "1",
                               "--runtime", "2026-10-05T10:09", "--target", self.tgt).stdout)
        self.assertTrue(again["already_started"])  # a re-run never rewinds the marker
        self.assertEqual(lc.ledger_target(text), self.tgt)

    def test_resolving_row_restarts_the_repeat_count(self):
        hdr = "| Runtime | Round | Phase | Cluster | Root cause | Address | Flags |\n|---|---|---|---|---|---|---|\n"
        def row(c, addr):
            return f"| 2026-10-06T10:00 | 1 | Prepass | {c} | sig-a | {addr} | |\n"
        led = Path(self._tmp.name) / "r.md"
        sig = lambda rc: rc or None  # noqa: E731
        clusters = [{"cluster": "C9", "flags": []}]
        csig = lambda c: "sig-a"  # noqa: E731
        led.write_text(hdr + row("C1", "FIX (a: x)") + row("C2", "FIX (a: y)"))
        fixer, paused = lc.split_repeat_clusters(led, 1, "Prepass", clusters, sig, csig)
        self.assertEqual((len(fixer), len(paused)), (0, 1))
        led.write_text(led.read_text() + row("C3", "FIX (a: z; resolves ORCHESTRATOR-PAUSE G1)"))
        fixer, paused = lc.split_repeat_clusters(led, 1, "Prepass", clusters, sig, csig)
        self.assertEqual((len(fixer), len(paused)), (1, 0))
        self.assertEqual(fixer[0]["resolutions"], 1)
        led.write_text(led.read_text() + row("C4", "FIX (a: p)") + row("C5", "FIX (a: q)"))
        fixer, paused = lc.split_repeat_clusters(led, 1, "Prepass", clusters, sig, csig)
        self.assertEqual((len(fixer), len(paused)), (0, 1))
        self.assertEqual(lc.auto_pause_report(paused)[0]["resolutions"], 1)

    def test_begin_round_refuses_other_target_and_adopts_on_legacy_ledger(self):
        other = Path(self._tmp.name) / "elsewhere" / "t"
        other.mkdir(parents=True)
        run("append_ledger.py", "begin-round", self.led, "--round", "1", "--runtime", "T1", "--target", self.tgt)
        before = Path(self.led).read_text()
        r = run("append_ledger.py", "begin-round", self.led, "--round", "2", "--runtime", "T2",
                "--target", str(other))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(Path(self.led).read_text(), before)  # nothing written
        # legacy ledger (no target:: line): the first target given is recorded, not refused
        Path(self.led).write_text(lc.ledger_header("t", "T1 prepass running round-1"))
        r = run("append_ledger.py", "begin-round", self.led, "--round", "1", "--runtime", "T1",
                "--target", str(other))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["target_recorded"])
        self.assertEqual(lc.ledger_target(Path(self.led).read_text()), str(other.resolve()))

    def test_close_round_reports_gate_on_reclose(self):
        run("append_ledger.py", "begin-round", self.led, "--round", "1", "--runtime", "T1", "--target", self.tgt)
        first = json.loads(run("append_ledger.py", "close-round", self.led, "--round", "1", "--converged").stdout)
        again = json.loads(run("append_ledger.py", "close-round", self.led, "--round", "1", "--converged").stdout)
        self.assertIn("gate", first)
        self.assertTrue(again["already_closed"])
        self.assertIn("gate", again)

    def test_fill_address_records_fix_and_close_accepts_it(self):
        run("append_ledger.py", "begin-round", self.led, "--round", "1", "--runtime", "T1", "--target", self.tgt)
        (Path(self.tgt) / "a.md").write_text("x\n")
        payload = json.dumps({"clusters": [{"cluster": "C1", "flags": ["P1"], "root_cause": "x"}]})
        self.assertEqual(run("ledger_cascade.py", self.led, "--runtime", "T1", "--round", "1",
                             "--mode", "cluster", "--phase", "Prepass", stdin=payload).returncode, 0)
        blast = Path(self._tmp.name) / "blast.json"
        blast.write_text(json.dumps({"blast_radius": [{"cluster": "C1", "fix_class": "LOCAL", "tokens": []}]}))
        dec = json.dumps({"decisions": [{"cluster": "C1", "decision": "FIX", "address": "FIX (a.md: edit)",
                                         "touched_files": ["a.md"]}]})
        r = run("ledger_cascade.py", self.led, "--runtime", "T1", "--round", "1", "--mode", "fill-address",
                "--phase", "Prepass", "--reenter", "--skill-root", self.tgt, "--blast-json", str(blast), stdin=dec)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = lc.round_rows(Path(self.led).read_text(), 1)
        self.assertTrue(rows[0]["address"].startswith("FIX ("))
        self.assertEqual(run("append_ledger.py", "close-round", self.led, "--round", "1").returncode, 0)

    def test_verify_only_flag_is_gone(self):
        r = run("ledger_cascade.py", self.led, "--runtime", "T1", "--round", "1", "--mode", "fill-address",
                "--phase", "Prepass", "--verify-only")
        self.assertEqual(r.returncode, 2)

    def test_fill_address_requires_phase(self):
        run("append_ledger.py", "begin-round", self.led, "--round", "1", "--runtime", "T1", "--target", self.tgt)
        r = run("ledger_cascade.py", self.led, "--runtime", "T1", "--round", "1", "--mode", "fill-address",
                stdin='{"decisions": []}')
        self.assertEqual(r.returncode, 2)

    def test_cluster_mode_supersedes_stale_pending_and_refuses_id_collision(self):
        run("append_ledger.py", "begin-round", self.led, "--round", "1", "--runtime", "T1", "--target", self.tgt)
        mk = lambda cid, flag: json.dumps({"clusters": [{"cluster": cid, "flags": [flag], "root_cause": "x"}]})
        args = ("--runtime", "T1", "--round", "1", "--mode", "cluster", "--phase", "Prepass")
        run("ledger_cascade.py", self.led, *args, stdin=mk("C1", "P1"))
        r = run("ledger_cascade.py", self.led, *args, stdin=mk("C2", "P2"))  # resume: C1 was never filled
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = [x["cluster"] for x in lc.round_rows(Path(self.led).read_text(), 1)]
        self.assertEqual(ids, ["C2"])
        # a different phase may not reuse an id that already exists in the round
        r = run("ledger_cascade.py", self.led, "--runtime", "T1", "--round", "1", "--mode", "cluster",
                "--phase", "Code Review", stdin=mk("C2", "G11"))
        self.assertEqual(r.returncode, 1)


class SmallHelpers(unittest.TestCase):
    def test_fixer_model_by_cluster_count(self):
        self.assertEqual(lc.fixer_model(1), "sonnet")
        self.assertEqual(lc.fixer_model(15), "sonnet")
        self.assertEqual(lc.fixer_model(16), "opus")

    def test_runtime_slug_and_pending(self):
        self.assertEqual(lc.runtime_slug("2026-10-05T10:00"), "2026-10-05T10-00")
        self.assertTrue(lc.is_pending("PENDING (considered-fix)"))
        self.assertFalse(lc.is_pending("FIX (a: b)"))



class LegacyMigration(unittest.TestCase):
    """Ledgers written by 3.0 with the minor-bugs tier marker keep working (the legacy mode/cr-mode run-options migration is tested in tests/test_round_gate.py)."""

    def test_minor_bugs_marker_resumes_as_code_review(self):
        m = lc.parse_in_flight("# Audit ledger — t\nin-flight:: T1 minor-bugs dispatched-3 round-2\n")
        self.assertEqual((m["phase"], m["state"], m["legacy_phase"]), ("code-review", "running", "minor-bugs"))
        self.assertTrue(m["phase_valid"] and m["state_valid"])
        self.assertNotIn("minor-bugs", lc.VALID_PHASES)

    def test_minor_bugs_phase_is_not_writable(self):
        with tempfile.TemporaryDirectory() as d:
            led, tgt = str(Path(d) / "t.md"), str(Path(d).resolve())
            run("append_ledger.py", "begin-round", led, "--round", "1", "--runtime", "T1", "--target", tgt)
            r = run("append_ledger.py", "append", led, "--runtime", "T1", "--round", "1", "--phase", "Minor Bugs",
                    "--cluster", "C1", "--root-cause", "x", "--flags", "B1", "--address", "FIX (a: b)",
                    "--blast-radius-status", "n/a: single-site change, no shared token")
            self.assertEqual(r.returncode, 1)


class InterfaceFreeze(unittest.TestCase):
    def test_run_round_counts_from_run_start(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "l.md"
            p.write_text("# Audit ledger — t\nrun-options:: run-start-round=5\n")
            self.assertEqual(lc.run_round(p, 5), 1)
            self.assertEqual(lc.run_round(p, 7), 3)
            self.assertEqual(lc.run_round(Path(d) / "absent.md", 3), 3)

    def test_interface_rule_frozen_from_round_1(self):
        for rnd in (1, 2, 3):
            rule = lc.interface_rule(rnd)
            self.assertIn("FROZEN", rule)
            self.assertNotIn("OPEN", rule)
            self.assertIn("ORCHESTRATOR-PAUSE", rule)
        rule = lc.interface_rule(1)
        for word in ("row kind", "shared helper module", "real behaviour bug", "fix the comment or doc, not the code"):
            self.assertIn(word, rule)

    def test_template_carries_the_slot(self):
        tpl = (SCRIPTS.parent / "templates" / "considered-fix.md").read_text()
        self.assertIn("[INTERFACE_RULE]", tpl)
        self.assertIn("deepest root fix that does not widen the interface", tpl)
        self.assertIn("[OUTPUT_CHECK]", tpl)
        self.assertLess(tpl.index("[OUTPUT_CHECK]"), tpl.index("## First instruction"))


if __name__ == "__main__":
    unittest.main()
