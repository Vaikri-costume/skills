"""Fixer batching and model rule (ledger_common.fixer_batches, cluster_enforce.py), the staged prompt's
output check (assemble_fix_prompt.py), the pre-record decision check (check_decisions.py) and
fill-address over several fixer transcripts (ledger_cascade.py).
Run: python3 -m unittest discover -s tests   (from the skill root)."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import ledger_common as lc  # noqa: E402

RT = "2026-10-05T10:00:00"


def run(script, *args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], input=stdin,
                          capture_output=True, text=True)


def fixer_transcript(path: Path, decisions: list) -> str:
    path.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "```json\n" + json.dumps({"decisions": decisions}) + "\n```"}]}}) + "\n")
    return str(path)


def doc(i):
    return {"cluster": f"C{i}", "members": [{"loc": f"references/r{i}.md:1"}]}


def code(i):
    return {"cluster": f"C{i}", "members": [{"loc": f"scripts/s{i}.py:1"}]}


class BatchSplit(unittest.TestCase):
    def test_twelve_or_fewer_is_one_batch_sonnet(self):
        clusters = [doc(i) if i % 2 else code(i) for i in range(1, 13)]  # 6 code, 6 doc
        [b] = lc.fixer_batches(clusters, [])
        self.assertEqual(b["model"], "sonnet")
        self.assertEqual(len(b["clusters"]), 12)
        self.assertEqual([c["cluster"] for c in b["clusters"]][:6], [f"C{i}" for i in (2, 4, 6, 8, 10, 12)])
        [b] = lc.fixer_batches([doc(i) for i in range(1, 13)], [])
        self.assertEqual(b["model"], "sonnet")

    def test_at_most_12_per_batch_code_first_with_model(self):
        clusters = [doc(i) if i % 2 else code(i) for i in range(1, 31)]  # 15 code, 15 doc
        batches = lc.fixer_batches(clusters, [])
        self.assertEqual([len(b["clusters"]) for b in batches], [12, 3, 12, 3])
        self.assertEqual([b["model"] for b in batches], ["opus"] * 4)  # 30 clusters: above 15
        self.assertEqual([b["batch"] for b in batches], [1, 2, 3, 4])
        ids = [c["cluster"] for b in batches for c in b["clusters"]]
        self.assertEqual(sorted(ids), sorted(c["cluster"] for c in clusters))  # each cluster exactly once
        self.assertTrue(all(len(b["clusters"]) <= lc.FIXER_BATCH_MAX_CLUSTERS for b in batches))

    def test_small_round_is_one_batch_and_blast_follows_its_clusters(self):
        blast = [{"cluster": "C1", "radius": ["references/r1.md:1"]}, {"cluster": "C2", "radius": []}]
        batches = lc.fixer_batches([doc(1), doc(2)], blast)
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["model"], "sonnet")
        self.assertEqual([b["cluster"] for b in batches[0]["blast"]], ["C1", "C2"])
        self.assertEqual(lc.fixer_batches([], []), [])


class StagedBatches(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.tgt, self.out, self.led = base / "target", base / "out", base / "t.md"
        self.tgt.mkdir()
        self.out.mkdir()
        (self.tgt / "SKILL.md").write_text("---\nname: t\n---\n# T\n")
        (self.tgt / "a.md").write_text("alpha\n")
        (self.tgt / "b.py").write_text("x = 1\n")
        run("append_ledger.py", "begin-round", str(self.led), "--round", "1", "--runtime", RT,
            "--target", str(self.tgt), "--set", "run-start-round=1")

    def tearDown(self):
        self._tmp.cleanup()

    def test_cluster_enforce_prints_batches_with_prompts_and_models(self):
        flags = [{"agent_flag": f"G1{i}", "file": "b.py" if i <= 2 else "a.md", "tag": "t",
                  "claim": f"{'b.py' if i <= 2 else 'a.md'}:{i} \"x\"", "target": f"distinct target {i}"}
                 for i in range(1, 16)]
        vf, cl = self.out / "vf.json", self.out / "cl.json"
        vf.write_text(json.dumps({"status": "verified-flags", "flags": flags}))
        cl.write_text(json.dumps({"clusters": [{"cluster": f"X{i}", "flags": [f["agent_flag"]]}
                                               for i, f in enumerate(flags, 1)]}))
        r = run("cluster_enforce.py", str(self.led), "--round", "1", "--runtime", RT, "--target", str(self.tgt),
                "--out-dir", str(self.out), "--verified-flags", str(vf), "--clusters", str(cl))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        batches = out["batches"]
        self.assertEqual([len(b["clusters"]) for b in batches], [2, 12, 1])  # 15 clusters: split
        self.assertEqual([b["model"] for b in batches], ["sonnet"] * 3)  # 15 clusters: not above 15
        for b in batches:
            text = Path(b["staged_prompt"]).read_text()
            self.assertIn(f"code-review-b{b['batch']}-", b["staged_prompt"])
            self.assertIn(", ".join(b["clusters"]), text)  # the batch's own ids in the output check
        self.assertIn("ONE AT A TIME", out["then"][0])
        self.assertIn("check_decisions.py", out["then"][1])

    def enforce(self, vf_obj, clusters):
        vf, cl = self.out / "vf2.json", self.out / "cl2.json"
        vf.write_text(json.dumps(vf_obj))
        cl.write_text(json.dumps({"clusters": clusters}))
        return run("cluster_enforce.py", str(self.led), "--round", "1", "--runtime", RT, "--target", str(self.tgt),
                   "--out-dir", str(self.out), "--verified-flags", str(vf), "--clusters", str(cl))

    def test_cluster_enforce_refuses_malformed_clusters_and_flagless_status(self):
        flags = [{"agent_flag": f"G1{i}", "file": "a.md", "tag": "t", "claim": f"a.md:{i} \"x\"",
                  "target": f"t{i}"} for i in (1, 2)]
        vf = {"status": "verified-flags", "flags": flags}
        for clusters in ([{"cluster": "C1", "flags": ["G11", "G12"]}, {"cluster": "C2", "flags": []}],
                         [{"cluster": "C1", "flags": ["G11"]}, {"cluster": "C1", "flags": ["G12"]}],
                         [{"flags": ["G11", "G12"]}]):
            r = self.enforce(vf, clusters)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertEqual(json.loads(r.stderr)["gate"], "no-drop")
        self.assertFalse(self.led.read_text().count("PENDING"))
        r = self.enforce({"status": "code-review-clean"}, [])
        self.assertEqual(r.returncode, 1)
        self.assertEqual(json.loads(r.stderr)["gate"], "verified-flags")

    def test_staged_prompt_states_contract_and_banned_vocabulary_first(self):
        [b] = lc.stage_fixer_batches(clusters=[doc(1)], blast=[], skill_root=self.tgt, rnd=1, runtime=RT,
                                     out_dir=self.out, label="prepass", run_rnd=1)
        text = Path(b["staged_prompt"]).read_text()
        head = text[:text.index("## First instruction")]
        self.assertIn('{"decisions": [...]}', head)
        for phrase in lc.BANNED_PHRASES:
            self.assertIn(phrase, head)
        self.assertIn("C1", head)
        self.assertIn("FROZEN", text)
        self.assertIn(lc.interface_rule(1), text)

    def test_no_new_behaviour_rule_is_identical_at_its_doc_sites(self):
        rule = lc.interface_rule(1)
        sentence = rule[rule.index("A fixer adds no new behaviour"):]
        root = SCRIPTS.parent
        for rel in ("SKILL.md", "references/how-to-fix.md", "references/glossary.md"):
            flat = " ".join((root / rel).read_text().split())
            self.assertIn(sentence, flat, rel)


class DecisionCheck(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def check(self, decisions, expect="C1,C2"):
        t = fixer_transcript(self.d / "f.jsonl", decisions)
        return run("check_decisions.py", "--fixer-transcript", t, "--expect", expect)

    CLOSURE = ["Siblings: SKILL.md:9 unchanged", "Bound: none added", "Claims: exit 1 -> s.py:40", "Blocks: none rewritten"]

    def test_clean_decisions_pass(self):
        r = self.check([{"cluster": "C1", "decision": "FIX", "address": "FIX (a.md: edit)",
                         "closure": self.CLOSURE},
                        {"cluster": "C2", "decision": "ORCHESTRATOR-PAUSE", "address": "Which form is intended?"}])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(json.loads(r.stdout)["ok"])

    def test_each_problem_is_reported(self):
        r = self.check([{"cluster": "C1", "decision": "FIX", "address": "STRENGTHEN (a.md:1: \"x\")"},
                        {"cluster": "C3", "decision": "STRENGTHEN", "address": ""},
                        {"cluster": "C3", "decision": "FIX", "address": "FIX (a.md: already correct, no change)"}])
        self.assertEqual(r.returncode, 1)
        kinds = {p["problem"] for p in json.loads(r.stdout)["problems"]}
        self.assertEqual(kinds, {"wrong-kind-prefix", "empty-address", "banned-vocabulary", "duplicate-cluster",
                                 "missing-cluster", "unknown-cluster", "missing-closure"})

    def test_fix_without_full_closure_is_refused_naming_the_cluster(self):
        fix = {"decision": "FIX", "address": "FIX (a.md: edit)"}
        r = self.check([dict(fix, cluster="C1"),
                        dict(fix, cluster="C2", closure=["Siblings: a.md:3 updated", "Bound:   ", "Claims: x -> a.md:3", "Blocks: none rewritten"])])
        self.assertEqual(r.returncode, 1)
        probs = [p for p in json.loads(r.stdout)["problems"] if p["problem"] == "missing-closure"]
        self.assertEqual([p["cluster"] for p in probs], ["C1", "C2"])
        self.assertIn("Siblings:, Bound:, Claims:, Blocks:", probs[0]["detail"])
        self.assertIn("Bound:", probs[1]["detail"])
        self.assertNotIn("Siblings:", probs[1]["detail"])

    def test_closure_is_required_only_on_fix(self):
        r = self.check([{"cluster": "C1", "decision": "STRENGTHEN", "address": "STRENGTHEN (added at a.md:2: \"why\")"},
                        {"cluster": "C2", "decision": "FIX", "address": "FIX (a.md: edit)", "closure": self.CLOSURE}])
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_staged_prompt_asks_for_the_closure_block(self):
        import assemble_fix_prompt as afp
        text = afp.output_check(["C1"])
        for label in ("Siblings:", "Bound:", "Claims:", "Blocks:"):
            self.assertIn(label, text)

    def test_not_json_is_a_problem_and_missing_file_is_usage(self):
        p = self.d / "t.jsonl"
        p.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant",
                                                                   "content": [{"type": "text", "text": "done"}]}}) + "\n")
        self.assertEqual(run("check_decisions.py", "--fixer-transcript", str(p)).returncode, 1)
        self.assertEqual(run("check_decisions.py", "--fixer-transcript", str(self.d / "absent.jsonl")).returncode, 2)


class FillAddressSeveralTranscripts(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.led, self.tgt = str(base / "t.md"), str(base)
        run("append_ledger.py", "begin-round", self.led, "--round", "1", "--runtime", "T1", "--target", self.tgt)
        payload = json.dumps({"clusters": [{"cluster": "C1", "flags": ["G11"], "root_cause": "x"},
                                           {"cluster": "C2", "flags": ["G12"], "root_cause": "y"}]})
        run("ledger_cascade.py", self.led, "--runtime", "T1", "--round", "1", "--mode", "cluster",
            "--phase", "Code Review", stdin=payload)
        self.blast = base / "blast.json"
        self.blast.write_text(json.dumps({"blast_radius": [{"cluster": "C1", "fix_class": "LOCAL"},
                                                           {"cluster": "C2", "fix_class": "LOCAL"}]}))
        self.t1 = fixer_transcript(base / "f1.jsonl", [{"cluster": "C1", "decision": "FIX", "address": "FIX (a.md: e)"}])
        self.t2 = fixer_transcript(base / "f2.jsonl", [{"cluster": "C2", "decision": "FIX", "address": "FIX (b.md: e)"}])

    def tearDown(self):
        self._tmp.cleanup()

    def fill(self, *transcript_args):
        return run("ledger_cascade.py", self.led, "--runtime", "T1", "--round", "1", "--mode", "fill-address",
                   "--phase", "Code Review", *transcript_args, "--skill-root", self.tgt, "--blast-json", str(self.blast))

    def test_repeated_option_records_every_batch(self):
        r = self.fill("--fixer-transcript", self.t1, "--fixer-transcript", self.t2)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["rows_filled"], 2)
        self.assertFalse(any(lc.is_pending(x["address"]) for x in lc.round_rows(Path(self.led).read_text(), 1)))

    def test_comma_list_and_duplicate_refusal(self):
        r = self.fill("--fixer-transcript", f"{self.t1},{self.t2}")
        self.assertEqual(r.returncode, 0, r.stderr)
        before = Path(self.led).read_text()
        r = self.fill("--fixer-transcript", f"{self.t1},{self.t1}")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(Path(self.led).read_text(), before)

    def test_no_decision_in_any_transcript_refuses_without_writing(self):
        base = Path(self.tgt)
        e1 = fixer_transcript(base / "e1.jsonl", [])
        e2 = base / "e2.jsonl"
        e2.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": json.dumps({"note": "done"})}]}}) + "\n")
        before = Path(self.led).read_text()
        r = self.fill("--fixer-transcript", f"{e1},{e2}")
        self.assertEqual(r.returncode, 2)
        self.assertIn("ERROR", r.stderr)
        self.assertEqual(Path(self.led).read_text(), before)

    def test_partial_decisions_still_auto_pause_the_rest(self):
        r = self.fill("--fixer-transcript", self.t1)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = {x["cluster"]: x["address"] for x in lc.round_rows(Path(self.led).read_text(), 1)}
        self.assertTrue(rows["C2"].startswith("ORCHESTRATOR-PAUSE"))


if __name__ == "__main__":
    unittest.main()
