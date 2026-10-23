#!/usr/bin/env python3
"""End-to-end smoke tests + fail-closed regression tests for the v0.2.0
review workflow, run against the tiny synthetic fixture book.

Run from the review_workflow/ directory:
    python3 -m unittest discover -s tests -v
or:
    python3 tests/test_workflow.py

Requires only the Python standard library plus Pillow (queue crops).
Every negative test maps to a release gate in V0.2.0_RELEASE_DECISION.md:
  R1 fail-closed lint / empty-OCR gates        -> lint & queue/score tests
  R2 relative crop paths + HTML escaping       -> queue display test
  R3 apply integrity (incomplete / duplicate /
     missing replacement / stale hash / spans) -> apply tests
  R4 configurability + synthetic fixture       -> the whole suite
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
FIXTURE = PKG / "fixtures" / "synthetic_book"


def run_tool(*args, expect=None):
    r = subprocess.run([sys.executable, "-m", "ocrqa.review_tool", *args],
                       cwd=PKG, capture_output=True, text=True)
    if expect is not None:
        assert (r.returncode == 0) == expect, \
            f"args={args} rc={r.returncode}\nstdout={r.stdout}\nstderr={r.stderr}"
    return r


def run_pipeline(*args):
    return subprocess.run([sys.executable, "-m", "ocrqa.pipeline", *args],
                          cwd=PKG, capture_output=True, text=True)


class BookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ocrqa-test-"))
        self.book = self.tmp / "book"
        shutil.copytree(FIXTURE, self.book)
        if not (self.book / "work/scans_360/p0101.png").exists():
            # Page images are binary and intentionally not committed; the
            # committed generator reproduces them deterministically.
            subprocess.run([sys.executable, str(PKG / "fixtures" / "make_fixture.py")],
                           cwd=PKG, capture_output=True, check=True)
            for pg in (101, 102):
                shutil.copy(FIXTURE / f"work/scans_360/p{pg:04d}.png",
                            self.book / f"work/scans_360/p{pg:04d}.png")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ---------------------------------------------------------
    def queue(self):
        return run_tool("queue", "--book-dir", str(self.book), expect=True)

    def mapping(self):
        self.queue()
        return json.loads((self.book / "queue/mapping_sealed.json").read_text())["items"]

    def decide(self, qid, decision, corrected="__unset__", expect=True):
        args = ["decide", "--book-dir", str(self.book), "--item", qid, "--decision", decision]
        if corrected != "__unset__":
            args += ["--corrected", corrected]
        return run_tool(*args, expect=expect)

    def decide_all_sensibly(self):
        mapping = self.mapping()
        for qid, m in mapping.items():
            if m["kind"] == "control":
                self.decide(qid, "KEEP")
            elif m["base_text"] == "'":
                self.decide(qid, "CONFIRM_FIX", "’")
            elif m["base_text"] == "":
                self.decide(qid, "CONFIRM_FIX", ".")
            else:
                self.decide(qid, "KEEP")
        return mapping


class TestLint(BookCase):
    def test_lint_ok(self):
        r = run_tool("lint", "--book-dir", str(self.book), expect=True)
        self.assertIn("LINT_OK", r.stdout)
        self.assertIn("normalize_before_score_selftest: PASS", r.stdout)

    def test_lint_corrupt_gold_fails_closed(self):  # R1
        p = self.book / "gold/p0101.txt"
        p.write_text(p.read_text().replace("harbour", "harboux"))
        r = run_tool("lint", "--book-dir", str(self.book), expect=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("MISMATCH", r.stdout + r.stderr)


class TestQueue(BookCase):
    def test_queue_counts(self):
        self.queue()
        out = json.loads((self.book / "queue/items.jsonl").read_text().splitlines()[0])
        self.assertTrue((self.book / "queue/queue.html").exists())
        mapping = json.loads((self.book / "queue/mapping_sealed.json").read_text())["items"]
        flags = [m for m in mapping.values() if m["kind"] == "flag"]
        ctrls = [m for m in mapping.values() if m["kind"] == "control"]
        self.assertEqual(len(flags), 5)          # designed loci F1..F5
        self.assertEqual(len(ctrls), len(flags))  # equal comparison items

    def test_queue_display_relative_paths_and_escaping(self):  # R2
        self.queue()
        page = (self.book / "queue/queue.html").read_text()
        self.assertIn('src="crops/Q', page)               # relative to queue.html
        self.assertNotIn('src="queue/crops/', page)       # the old broken path
        self.assertIn("a&lt;b", page)                    # OCR text escaped
        self.assertNotIn("a<b and", page)                 # never raw markup
        items = [json.loads(l) for l in (self.book / "queue/items.jsonl").read_text().splitlines()]
        for it in items:                                  # every crop resolves
            self.assertTrue((self.book / "queue" / it["crop"]).exists(), it["crop"])

    def test_queue_empty_tier_fails_closed(self):  # R1
        (self.book / "work/ocr_300/p0102.txt").write_bytes(b"")
        r = run_tool("queue", "--book-dir", str(self.book), expect=False)
        self.assertEqual(r.returncode, 3)
        self.assertIn("EMPTY_OCR_OUTPUT", r.stderr)
        self.assertIn("102", r.stderr)


class TestDecideApplyScore(BookCase):
    def test_end_to_end(self):
        mapping = self.decide_all_sensibly()
        r = run_tool("apply", "--book-dir", str(self.book), expect=True)
        self.assertEqual(json.loads(r.stdout)["applied"], 3)
        r = run_tool("score", "--book-dir", str(self.book), expect=True)
        res = json.loads((self.book / "eval_results.json").read_text())
        self.assertEqual(res["edits_before"], 3)
        self.assertEqual(res["edits_after"], 0)
        self.assertLess(res["cer_after"], res["cer_before"])
        self.assertEqual(res["true_positives"], 3)
        self.assertEqual(res["false_positives"], 0)
        self.assertAlmostEqual(res["human_yield"], 0.6)
        self.assertAlmostEqual(res["human_coverage"], 1.0)
        self.assertAlmostEqual(res["mechanical_hit_rate"], 0.6)
        self.assertEqual(res["control_group"]["confirmed_errors"], 0)

    def test_original_ocr_never_touched(self):
        before = (self.book / "work/ocr_200/p0101.txt").read_bytes()
        self.decide_all_sensibly()
        run_tool("apply", "--book-dir", str(self.book), expect=True)
        self.assertEqual((self.book / "work/ocr_200/p0101.txt").read_bytes(), before)

    def test_decide_confirm_fix_requires_replacement(self):  # R3
        mapping = self.mapping()
        qid = next(q for q, m in mapping.items() if m["kind"] == "flag")
        r = self.decide(qid, "CONFIRM_FIX", expect=False)
        self.assertEqual(r.returncode, 4)

    def test_decide_duplicate_rejected(self):  # R3
        mapping = self.mapping()
        qid = next(iter(mapping))
        self.decide(qid, "KEEP")
        r = self.decide(qid, "KEEP", expect=False)
        self.assertEqual(r.returncode, 4)

    def test_apply_incomplete_refused_and_writes_nothing(self):  # R3
        mapping = self.mapping()
        qid = next(iter(mapping))
        self.decide(qid, "KEEP")
        r = run_tool("apply", "--book-dir", str(self.book), expect=False)
        self.assertEqual(r.returncode, 5)
        self.assertFalse((self.book / "corrected").exists())

    def test_apply_missing_replacement_refused(self):  # R3 (decisions file edited by hand)
        mapping = self.mapping()
        lines = []
        for qid, m in mapping.items():
            fix = m["kind"] == "flag" and m["base_text"] == "'"
            lines.append(json.dumps({"ts": "2026-01-01T00:00:00+00:00", "item_id": qid,
                                     "page": m["page"], "decision": "CONFIRM_FIX" if fix else "KEEP",
                                     "corrected": None if fix else None, "note": "", "crop": "",
                                     "context": ""}))
        (self.book / "decisions.jsonl").write_text("\n".join(lines) + "\n")
        r = run_tool("apply", "--book-dir", str(self.book), expect=False)
        self.assertEqual(r.returncode, 5)
        self.assertIn("without replacement", r.stderr)

    def test_apply_duplicate_records_refused(self):  # R3
        mapping = self.decide_all_sensibly()
        log = self.book / "decisions.jsonl"
        first = log.read_text().splitlines()[0]
        with log.open("a") as fh:
            fh.write(first + "\n")
        r = run_tool("apply", "--book-dir", str(self.book), expect=False)
        self.assertEqual(r.returncode, 5)
        self.assertIn("duplicate", r.stderr)

    def test_apply_stale_source_refused(self):  # R3
        self.decide_all_sensibly()
        p = self.book / "work/ocr_200/p0101.txt"
        p.write_text(p.read_text() + "tampered")
        r = run_tool("apply", "--book-dir", str(self.book), expect=False)
        self.assertEqual(r.returncode, 5)
        self.assertIn("changed since queue build", r.stderr)

    def test_apply_overlapping_spans_refused(self):  # R3
        mapping = self.decide_all_sensibly()
        mp = self.book / "queue/mapping_sealed.json"
        doc = json.loads(mp.read_text())
        decided = {json.loads(l)["item_id"]: json.loads(l)
                   for l in (self.book / "decisions.jsonl").read_text().splitlines()}
        fixes = [q for q, m in doc["items"].items()
                 if m["kind"] == "flag" and m["page"] == 101
                 and decided[q]["decision"] == "CONFIRM_FIX"]
        self.assertGreaterEqual(len(fixes), 2)
        doc["items"][fixes[1]]["base_span"] = doc["items"][fixes[0]]["base_span"]
        mp.write_text(json.dumps(doc))
        r = run_tool("apply", "--book-dir", str(self.book), expect=False)
        self.assertEqual(r.returncode, 5)
        self.assertIn("conflicting fix spans", r.stderr)

    def test_score_tampered_gold_fails_closed(self):  # R1
        self.decide_all_sensibly()
        run_tool("apply", "--book-dir", str(self.book), expect=True)
        p = self.book / "gold/p0102.txt"
        p.write_text(p.read_text().replace("rain", "snow"))
        r = run_tool("score", "--book-dir", str(self.book), expect=False)
        self.assertEqual(r.returncode, 2)

    def test_score_empty_tier_fails_closed(self):  # R1
        self.decide_all_sensibly()
        run_tool("apply", "--book-dir", str(self.book), expect=True)
        (self.book / "work/ocr_360/p0101.txt").write_bytes(b"")
        r = run_tool("score", "--book-dir", str(self.book), expect=False)
        self.assertEqual(r.returncode, 3)


class TestPipelineGate(unittest.TestCase):
    """R1 for the OCR pipeline, tested with pre-seeded outputs so no
    Poppler/Tesseract is needed: the gate logic is what is under test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ocrqa-pipe-"))
        self.work = self.tmp / "work"
        self.pdf = self.tmp / "fake.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 synthetic\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def seed(self, pg=5, empty_tier=None):
        for d in ("scans", "scans_300", "scans_360", "flat_200", "flat_300", "flat_360",
                  "ocr_200", "ocr_300", "ocr_360", "tsv"):
            (self.work / d).mkdir(parents=True, exist_ok=True)
        for d in ("scans", "scans_300", "scans_360", "flat_200", "flat_300", "flat_360"):
            (self.work / d / f"p{pg:04d}.png").write_bytes(b"\x89PNG")
        for tier in (200, 300, 360):
            data = b"" if tier == empty_tier else b"some ocr text\n"
            (self.work / f"ocr_{tier}" / f"p{pg:04d}.txt").write_bytes(data)
        (self.work / "tsv" / f"p{pg:04d}.tsv").write_text("level\ttext\n")

    def test_empty_output_fails_closed(self):
        self.seed(empty_tier=300)
        r = run_pipeline("--pdf", str(self.pdf), "--pages", "5", "--work-dir", str(self.work))
        self.assertEqual(r.returncode, 3)
        self.assertIn("EMPTY_OCR_GATE_FAILED", r.stderr)

    def test_nonempty_ok(self):
        self.seed()
        r = run_pipeline("--pdf", str(self.pdf), "--pages", "5", "--work-dir", str(self.work))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PIPELINE_OK", r.stdout)

    def test_declared_blank_page_is_the_only_exception(self):
        self.seed(empty_tier=200)
        r = run_pipeline("--pdf", str(self.pdf), "--pages", "5", "--work-dir", str(self.work),
                         "--blank-pages", "5")
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
