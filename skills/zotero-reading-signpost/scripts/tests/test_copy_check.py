import subprocess, sys, tempfile, pathlib

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "copy_check.py"
SRC = "Mimicry is the desire for a reformed, recognizable Other, as a subject of a difference that is almost the same, but not quite."


def run(summary, comments=None):
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "s.txt").write_text(SRC)
        (d / "m.md").write_text(summary)
        cmd = [sys.executable, "-I", str(SCRIPT), str(d / "s.txt"), str(d / "m.md")]
        if comments is not None:
            (d / "c.txt").write_text("\n".join(comments))
            cmd += ["--comments", str(d / "c.txt")]
        return subprocess.run(cmd, capture_output=True, text=True)


def test_flags_copied_clause():
    r = run("Mimicry is the desire for a reformed recognizable Other here.")
    assert r.returncode == 1 and "FLAG" in r.stdout


def test_passes_new_wording():
    r = run("Colonial rulers want natives who copy them closely yet always remain visibly lesser.")
    assert r.returncode == 0


def test_comment_phrases_are_not_flagged():
    s = "Mimicry is the desire for a reformed recognizable Other here."
    assert run(s).returncode == 1
    assert run(s, ["the desire for a reformed recognizable Other"]).returncode == 0


def test_connecting_prose_still_flagged_with_comments():
    s = "Mimicry is the desire for a reformed recognizable Other here, which is almost the same but not quite."
    r = run(s, ["almost the same"])
    assert r.returncode == 1 and "desire for a reformed" in r.stdout


def test_paragraph_starting_with_status_is_checked():
    r = run("Status hierarchies are kept; Mimicry is the desire for a reformed recognizable Other here.\n\nMimicry is the desire for a reformed recognizable Other here.")
    assert r.returncode == 1 and "FLAG" in r.stdout
    r = run("Status hierarchies: mimicry is the desire for a reformed recognizable Other.")
    assert r.returncode == 1 and "FLAG" in r.stdout


def test_count_lines_are_skipped():
    for line in ("Status: mimicry is the desire for a reformed recognizable Other.",
                 "Word count: mimicry is the desire for a reformed recognizable Other.",
                 "SENTENCES : mimicry is the desire for a reformed recognizable Other."):
        assert run(line).returncode == 0, line


def test_comment_cut_across_line_break_and_curly_quotes():
    assert run("Mimicry is the desire for a\nreformed recognizable Other here.").returncode == 1
    assert run("Mimicry is the desire for a\nreformed recognizable Other here.", ["The Desire for a reformed recognizable other"]).returncode == 0
    s = "Mimicry is \u2018the desire for a reformed recognizable Other\u2019 here."
    assert run(s.replace("\u2018", "").replace("\u2019", "")).returncode == 1
    assert run("Mimicry isn\u2019t the desire for a reformed recognizable Other here.", ["isn't the desire for a reformed recognizable Other"]).returncode == 0


def test_comment_cut_requires_word_boundaries():
    s = "Mimicry is the desire for a reformed recognizable Others here."
    assert run(s, ["the desire for a reformed recognizable Other"]).returncode == 1
    s = "Mimicry is the desire for a reformed recognizable Other here."
    assert run(s, ["the desire for a reformed recognizable Other"]).returncode == 0


def test_comment_containing_quotation_marks_is_cut_before_quotes_are_stripped():
    s = "Mimicry is the \u201cdesire for a reformed\u201d recognizable Other here."
    assert run(s, ['is the "desire for a reformed" recognizable Other']).returncode == 0


def test_quoted_span_of_any_length_is_ignored():
    s = "\u201cMimicry is the desire for a reformed recognizable Other as a subject of a difference\u201d here."
    assert run(s).returncode == 0


def test_curly_single_quoted_term_is_ignored_but_apostrophe_kept():
    # The quoted term copies the source; the apostrophe in "women's" must not start a quoted span.
    r = run("Bhabha calls it ‘a reformed, recognizable Other, as a subject of a difference’ in women's terms.")
    assert "FLAG" not in r.stdout, r.stdout


def test_undecodable_input_exits_2():
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "s.txt").write_bytes(b"\xff\xfe\xfa not utf-8")
        (d / "m.md").write_text("A summary sentence of some words here.")
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(d / "s.txt"), str(d / "m.md")], capture_output=True, text=True)
        assert r.returncode == 2, r.stdout + r.stderr


def test_bad_numeric_options_exit_2():
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "s.txt").write_text(SRC)
        (d / "m.md").write_text("Some plain summary words here today.")
        for opt in ("--ratio", "--run"):
            for extra in ([opt, "abc"], [opt]):
                r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(d / "s.txt"), str(d / "m.md"), *extra], capture_output=True, text=True)
                assert r.returncode == 2 and "Traceback" not in r.stderr, (extra, r.returncode, r.stderr)


def test_missing_comments_value_has_own_message():
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "s.txt").write_text(SRC)
        (d / "m.md").write_text("Some plain summary words here today.")
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(d / "s.txt"), str(d / "m.md"), "--comments"], capture_output=True, text=True)
        assert r.returncode == 2 and "missing --comments file" in r.stdout and "--ratio" not in r.stdout
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(d / "s.txt"), str(d / "m.md"), "--run", "abc"], capture_output=True, text=True)
        assert r.returncode == 2 and "bad --run value" in r.stdout


def run_src(src, summary):
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "s.txt").write_text(src)
        (d / "m.md").write_text(summary)
        return subprocess.run([sys.executable, "-I", str(SCRIPT), str(d / "s.txt"), str(d / "m.md")], capture_output=True, text=True)


def test_compound_broken_at_line_end_is_flagged():
    src = "Reform favours a market-\ndriven economy over state planning."
    r = run_src(src, "Reform favours a market-driven economy over state planning.")
    assert r.returncode == 1 and "FLAG" in r.stdout


def test_soft_hyphen_at_line_end_still_joins():
    src = "The gov-\nernment keeps careful records of every transaction."
    r = run_src(src, "The government keeps careful records of every transaction.")
    assert r.returncode == 1 and "FLAG" in r.stdout


class CopyCheckTests(__import__("unittest").TestCase):
    """Runs the test functions above under `python3 -m unittest discover`, which collects only TestCase classes."""


for _name, _fn in list(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        setattr(CopyCheckTests, _name, staticmethod(_fn))
del _name, _fn  # the loop variable would otherwise leave the class under a second name, collected twice


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as e:
                failed += 1
                print("FAIL", name, e)
    print("FAILED" if failed else "OK")
    sys.exit(1 if failed else 0)
