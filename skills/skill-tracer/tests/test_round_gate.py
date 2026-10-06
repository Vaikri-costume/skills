"""Unit tests for the round gate and run-options persistence (scripts/ledger_common.py).
Run: python3 -m unittest discover -s tests   (from the skill root)."""
import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ledger_common as lc  # noqa: E402


def ledger(counts, opts=""):
    rows = "".join(
        f"<!-- Round {i} total: raw flags {c} — clusters 1 — addresses: 1 FIX + 0 STRENGTHEN + 0 ORCHESTRATOR-PAUSE + 0 USER-PAUSE -->\n"
        for i, c in enumerate(counts, 1))
    return f"# Audit ledger — t\n{opts}\n{rows}"


class RoundGate(unittest.TestCase):
    def test_continue_when_shrinking(self):
        g = lc.round_gate(ledger([20, 12, 8, 5, 3]), 5)
        self.assertTrue(g["continue"])

    def test_stalled_when_last_three_never_beat_best(self):
        g = lc.round_gate(ledger([9, 8, 9, 9, 9]), 5)
        self.assertEqual(g["stop"], "stalled")

    def test_plateau_stalls_by_design(self):
        # evals iteration 5 shape 21,6,3,3,4,3,3,...: a plateau at the best count for 3 rounds stops the
        # run as "stalled" (not converged). Calibration choice: 3 rounds without a new best is a stall.
        self.assertEqual(lc.round_gate(ledger([21, 6, 3, 3, 4, 3, 3]), 7)["stop"], "stalled")

    def test_wobble_with_new_best_continues(self):
        self.assertTrue(lc.round_gate(ledger([21, 6, 4, 4, 5, 3]), 6)["continue"])

    def test_round_cap_default_8(self):
        self.assertEqual(lc.round_gate(ledger([50, 40, 30, 20, 10, 9, 8, 7]), 8)["stop"], "round-cap")

    def test_max_rounds_option_and_run_start(self):
        text = ledger([5, 4, 3, 2, 1], "run-options:: max-rounds=2 run-start-round=4")
        self.assertEqual(lc.round_gate(text, 5)["stop"], "round-cap")

    def test_budget_exhausted(self):
        text = ledger([9, 8], "run-options:: rounds-budget=2 run-start-round=1")
        self.assertEqual(lc.round_gate(text, 2)["stop"], "budget-exhausted")


class RunOptions(unittest.TestCase):
    def test_roundtrip_and_reject_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "l.md"
            p.write_text("# Audit ledger — t\n")
            lc.write_run_options(p, {"rounds-budget": 3, "max-rounds": 10})
            lc.write_run_options(p, {"run-start-round": 4})
            opts = lc.parse_run_options(p.read_text())
            self.assertEqual(opts, {"rounds-budget": "3", "max-rounds": "10", "run-start-round": "4"})
            lc.write_run_options(p, {"rounds-budget": ""})  # empty value removes the key
            self.assertNotIn("rounds-budget", lc.parse_run_options(p.read_text()))
            for bad in ({"bogus": 1}, {"mode": "one-round"}, {"cr-mode": "specialist"}, {"max-rounds": 0}):
                with self.assertRaises(ValueError):
                    lc.write_run_options(p, bad)

    def test_legacy_v1_keys_are_migrated(self):
        one = lc.parse_run_options("run-options:: mode=one-round cr-mode=specialist run-start-round=2\n")
        self.assertEqual(one, {"rounds-budget": "1", "run-start-round": "2"})
        kept = lc.parse_run_options("run-options:: mode=one-round rounds-budget=4\n")
        self.assertEqual(kept, {"rounds-budget": "4"})
        dropped = lc.parse_run_options("run-options:: mode=verify-only max-rounds=3\n")
        self.assertEqual(dropped, {"max-rounds": "3"})

    def test_legacy_line_is_rewritten_as_v2(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "l.md"
            p.write_text("# Audit ledger — t\nrun-options:: mode=one-round cr-mode=generalist\n")
            lc.write_run_options(p, {"max-rounds": 5})
            text = p.read_text()
            self.assertNotIn("mode=", text)
            self.assertEqual(lc.parse_run_options(text), {"rounds-budget": "1", "max-rounds": "5"})


if __name__ == "__main__":
    unittest.main()
