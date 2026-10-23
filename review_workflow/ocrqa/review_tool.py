#!/usr/bin/env python3
"""review_tool.py — human-in-the-loop OCR punctuation review workflow (v0.2.0).

This is a REVIEW-ASSIST tool, not an automatic corrector. The frozen P16
three-DPI disagreement detector proposes candidate spans; a human judges
each one against the page image; only explicitly confirmed fixes are ever
written, and only to a separate corrected/ copy. Original OCR is never
modified.

Subcommands:
  lint    Verify the gold seal (SHA-256 per file) and gold sanity.
          FAIL-CLOSED (R1): any seal mismatch or missing/empty gold file
          for a non-blank page exits nonzero.
  queue   Build the blind review queue: detector flags + an equal number
          of randomly sampled baseline punctuation positions (comparison
          items), shuffled under neutral IDs. Every item gets a crop from
          the 360-DPI page image. FAIL-CLOSED (R1): any missing/empty OCR
          tier file for a non-blank page exits nonzero.
          Display (R2): queue.html references crops by paths relative to
          the HTML file itself, and all OCR text is HTML-escaped.
  decide  Append one timestamped decision per item. CONFIRM_FIX requires
          an explicit --corrected replacement (an empty string is a valid
          explicit deletion). Duplicate decisions are rejected (R3).
  apply   Write corrected/ copies. FAIL-CLOSED (R3): refuses and writes
          nothing when the review is incomplete, decision IDs are
          duplicated/unknown, a CONFIRM_FIX lacks its replacement, spans
          of confirmed fixes overlap, or the baseline OCR changed since
          the queue was built (source-hash check).
  score   Dual-track scoring (human decisions / mechanical span overlap),
          site census, efficiency metrics, comparison-item results.
          FAIL-CLOSED (R1): seal mismatch or empty tier file exits
          nonzero, so a corrupted setup cannot yield a "successful" score.

Configuration (R4): the book directory holds a book.json:
  {"pages": [101, 102], "blank_pages": [],
   "gold_dir": "gold", "seal": "gold_seal.json",
   "tiers": [200, 300, 360], "baseline_tier": 200, "crop_tier": 360,
   "control_seed": 20261023}
`blank_pages` lists pages verified against the source to be blank plates;
they are the ONLY pages allowed to have empty gold/OCR files, and the
exception is explicit in every gate output.
--pages overrides the manifest page list.

Blindness, stated accurately (R3): item IDs are neutral and flag/control
kinds are concealed in a separate mapping file, but the mapping is an
ordinary readable file (convention, not cryptography), and the displayed
three-tier readings can let a reviewer infer which items are flags. This
is an ID-concealed mixed queue, NOT a strict double-blind trial.

Exit codes: 0 ok; 2 lint/seal failure; 3 missing/empty OCR input;
4 decision error; 5 apply refused; 6 configuration error.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import html
import json
import random
import sys
from datetime import datetime
from pathlib import Path

try:
    from .textnorm import normalize, levenshtein
    from . import detector as det
except ImportError:  # direct script context
    from textnorm import normalize, levenshtein
    import detector as det

PUNCT_CHARS = ".,;:!?‘’'\"“”«»-—–*"

EXIT_OK, EXIT_LINT, EXIT_INPUT, EXIT_DECIDE, EXIT_APPLY, EXIT_CONFIG = 0, 2, 3, 4, 5, 6


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def die(code: int, msg: str) -> "SystemExit":
    print(msg, file=sys.stderr)
    raise SystemExit(code)


# ---------------------------------------------------------------- config
class Book:
    def __init__(self, book_dir: Path, pages_override: str | None = None):
        self.dir = Path(book_dir)
        cfg_path = self.dir / "book.json"
        if not cfg_path.exists():
            die(EXIT_CONFIG, f"CONFIG_ERROR: {cfg_path} missing — a book manifest is required (see README).")
        try:
            self.cfg = json.loads(cfg_path.read_text())
        except Exception as e:  # noqa: BLE001
            die(EXIT_CONFIG, f"CONFIG_ERROR: cannot parse {cfg_path}: {e}")
        pages = self.cfg.get("pages")
        if pages_override:
            pages = [int(x) for x in pages_override.split(",") if x.strip()]
        if not pages:
            die(EXIT_CONFIG, "CONFIG_ERROR: no pages configured (book.json 'pages' or --pages).")
        self.pages = [int(p) for p in pages]
        self.blank_pages = {int(p) for p in self.cfg.get("blank_pages", [])}
        self.gold_dir = self.dir / self.cfg.get("gold_dir", "gold")
        self.seal = self.dir / self.cfg.get("seal", "gold_seal.json")
        self.tiers = [int(t) for t in self.cfg.get("tiers", [200, 300, 360])]
        self.baseline = int(self.cfg.get("baseline_tier", 200))
        self.crop_tier = int(self.cfg.get("crop_tier", 360))
        self.control_seed = int(self.cfg.get("control_seed", 20261023))

    def tier_path(self, tier: int, pg: int) -> Path:
        return self.dir / f"work/ocr_{tier}/p{pg:04d}.txt"

    def tier_text(self, tier: int, pg: int) -> str:
        return normalize(self.tier_path(tier, pg).read_text(encoding="utf-8"))

    def gold_text(self, pg: int) -> str:
        return normalize((self.gold_dir / f"p{pg:04d}.txt").read_text(encoding="utf-8"))

    def scan_path(self, pg: int) -> Path:
        d = "work/scans" if self.crop_tier == 200 else f"work/scans_{self.crop_tier}"
        return self.dir / f"{d}/p{pg:04d}.png"

    def gate_inputs(self, need_tiers: bool = True, need_gold: bool = True) -> None:
        """R1 fail-closed input gate shared by queue/score."""
        problems = []
        if need_tiers:
            for pg in self.pages:
                if pg in self.blank_pages:
                    continue
                for tier in self.tiers:
                    p = self.tier_path(tier, pg)
                    if not p.exists():
                        problems.append(f"page {pg} tier {tier}: MISSING {p}")
                    elif p.stat().st_size == 0:
                        problems.append(f"page {pg} tier {tier}: EMPTY_OCR_OUTPUT {p}")
        if need_gold:
            for pg in self.pages:
                if pg in self.blank_pages:
                    continue
                p = self.gold_dir / f"p{pg:04d}.txt"
                if not p.exists():
                    problems.append(f"page {pg}: MISSING gold {p}")
                elif p.stat().st_size == 0:
                    problems.append(f"page {pg}: EMPTY gold {p}")
        if problems:
            die(EXIT_INPUT, "INPUT_GATE_FAILED (fail-closed):\n" + "\n".join(problems))

    def gate_seal(self) -> None:
        if verify_seal(self) > 0:
            die(EXIT_LINT, "SEAL_GATE_FAILED (fail-closed): gold seal mismatch — refusing to proceed.")


def verify_seal(book: Book) -> int:
    """Return number of mismatches; print per-file evidence."""
    if not book.seal.exists():
        print(f"seal file missing: {book.seal}")
        return 1
    seal = json.loads(book.seal.read_text())
    files = seal.get("files", seal)
    bad = 0
    for name, want in sorted(files.items()):
        p = book.gold_dir / name
        if not p.exists():
            print(f"seal {name}: MISSING"); bad += 1; continue
        got = sha256(p)
        ok = got == want
        print(f"seal {name}: {'OK' if ok else 'MISMATCH'}")
        bad += 0 if ok else 1
    return bad


# ------------------------------------------------------------------ lint
def cmd_lint(a) -> int:
    book = Book(a.book_dir, a.pages)
    bad = verify_seal(book)
    warns = 0
    for pg in book.pages:
        p = book.gold_dir / f"p{pg:04d}.txt"
        if p.exists():
            warns += p.read_text(encoding="utf-8").count("'")
    print(f"ascii_apostrophe_warnings: {warns} (WARNING ONLY — inspect the plate; never auto-replace)")
    # normalize-before-score self-test (P16 erratum regression): deleting a
    # spurious " :" token leaves a double space; scoring the RAW string then
    # overcounts by exactly one edit, scoring the normalized string does not.
    g = "alpha beta"
    fixed = "alpha  beta"   # double space left by a deletion
    raw = levenshtein(fixed, g)
    normed = levenshtein(normalize(fixed), g)
    st = "PASS" if (raw == 1 and normed == 0) else "FAIL"
    print(f"normalize_before_score_selftest: {st}")
    if st == "FAIL":
        return EXIT_LINT
    if bad:
        print(f"LINT_SEAL_MISMATCH: {bad} file(s) — FAIL-CLOSED")
        return EXIT_LINT
    book.gate_inputs(need_tiers=False, need_gold=True)
    print("LINT_OK")
    return EXIT_OK


# ----------------------------------------------------------------- queue
def word_boxes(book: Book, pg: int):
    tsv = book.dir / f"work/tsv/p{pg:04d}.tsv"
    words, pos = [], 0
    if not tsv.exists():
        return words
    with tsv.open(newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row.get("level") != "5" or not row.get("text"):
                continue
            w = row["text"]
            words.append({"text": w, "start": pos, "end": pos + len(w),
                          "left": int(row["left"]), "top": int(row["top"]),
                          "width": int(row["width"]), "height": int(row["height"])})
            pos += len(w) + 1
    return words


def make_crop(book: Book, pg: int, base_off: int, out: Path) -> str:
    from PIL import Image
    words = word_boxes(book, pg)
    box = next((w for w in words if w["start"] <= base_off < w["end"]), None)
    if box is None:
        box = next((w for w in words if abs(w["start"] - base_off) <= 3 or abs(w["end"] - base_off) <= 3), None)
    img_path = book.scan_path(pg)
    im = Image.open(img_path)
    scale = book.crop_tier / book.baseline
    if box is not None:
        l, t = box["left"], box["top"]
        w, h = max(box["width"], 30), max(box["height"], 14)
        x0, y0 = int((l - w * 0.9) * scale), int((t - h * 0.55) * scale)
        x1, y1 = int((l + w * 1.9) * scale), int((t + h * 1.55) * scale)
        method = "tsv_word_box"
    else:
        base = book.tier_text(book.baseline, pg)
        frac = base_off / max(1, len(base))
        cw, ch = im.width, im.height
        y = int(frac * ch)
        x0, y0, x1, y1 = 0, max(0, y - ch // 28), cw, min(ch, y + ch // 28)
        method = "page_fraction_fallback"
    crop = im.crop((max(0, x0), max(0, y0), min(im.width, x1), min(im.height, y1)))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out)
    return method


def cmd_queue(a) -> int:
    book = Book(a.book_dir, a.pages)
    book.gate_seal()
    book.gate_inputs()
    qdir = book.dir / "queue"
    (qdir / "crops").mkdir(parents=True, exist_ok=True)
    entries, source_hashes = [], {}
    for pg in book.pages:
        if pg in book.blank_pages:
            continue
        base = book.tier_text(book.baseline, pg)
        others = {t: book.tier_text(t, pg) for t in book.tiers if t != book.baseline}
        flags = det.detect(base, *[others[t] for t in sorted(others)]) if len(others) == 2 \
            else die(EXIT_CONFIG, "CONFIG_ERROR: the frozen detector needs exactly two comparison tiers.")
        for fl in flags:
            fl["page"] = pg
            entries.append({"kind": "flag", "ref": fl})
        spans = [tuple(fl["base_span"]) for fl in flags]
        rng = random.Random(book.control_seed + pg)
        cand = [i for i, ch in enumerate(base)
                if ch in PUNCT_CHARS and all(not (s - 2 <= i <= e + 2) for s, e in spans)]
        rng.shuffle(cand)
        for i in cand[:len(flags)]:
            entries.append({"kind": "control", "ref": {"page": pg, "pos": i}})
        source_hashes[str(pg)] = sha256(book.tier_path(book.baseline, pg))
    rng = random.Random(book.control_seed)
    rng.shuffle(entries)
    items, mapping = [], {}
    for n, entry in enumerate(entries, 1):
        qid = f"Q{n:03d}"
        if entry["kind"] == "flag":
            fl = entry["ref"]
            pg, (s, e) = fl["page"], fl["base_span"]
            base = book.tier_text(book.baseline, pg)
            pos = sorted(fl["positions"], key=lambda p: p["base_index"])

            def rd(key):
                return "".join(p[key] if p[key] is not None else "∅" for p in pos)
            item = {"item_id": qid, "page": pg, "base_span": [s, e],
                    "context": base[max(0, s - 45):e + 45],
                    "readings": {str(book.baseline): base[s:e], "300": rd("reading_300"), "360": rd("reading_360")},
                    "category": "punct_disagreement", "base_text": fl["base_text"]}
            mapping[qid] = {"kind": "flag", "page": pg, "base_span": [s, e],
                            "category": "punct_disagreement", "base_text": fl["base_text"]}
            crop_off = s
        else:
            pg, i = entry["ref"]["page"], entry["ref"]["pos"]
            base = book.tier_text(book.baseline, pg)
            item = {"item_id": qid, "page": pg, "base_span": [i, i + 1],
                    "context": base[max(0, i - 45):i + 46],
                    "readings": {str(book.baseline): base[i:i + 1]},
                    "category": "punct_site"}
            mapping[qid] = {"kind": "control", "page": pg, "pos": i}
            crop_off = i
        crop_rel = f"crops/{qid}.png"           # R2: relative to queue.html itself
        method = make_crop(book, pg, crop_off, qdir / crop_rel)
        if not (qdir / crop_rel).exists():
            die(EXIT_INPUT, f"CROP_GATE_FAILED: crop not created for {qid} (page {pg})")
        item["crop"] = crop_rel
        item["crop_method"] = method
        items.append(item)
    (qdir / "items.jsonl").write_text(
        "".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items))
    (qdir / "mapping_sealed.json").write_text(json.dumps(
        {"note": "ID-concealed kind mapping. Ordinary readable file: concealment is by "
                 "workflow convention, NOT cryptographic sealing. Do not open before all "
                 "decisions are recorded; tooling opens it only in apply/score.",
         "detector_sha256": sha256(Path(det.__file__)),
         "source_ocr_sha256": source_hashes, "items": mapping}, indent=1, ensure_ascii=False) + "\n")
    (qdir / "queue_manifest.json").write_text(json.dumps(
        {"pages": book.pages, "blank_pages": sorted(book.blank_pages),
         "source_ocr_sha256": source_hashes,
         "detector_sha256": sha256(Path(det.__file__)),
         "built_at": datetime.now().astimezone().isoformat(timespec="seconds")}, indent=1) + "\n")
    rows = []
    for it in items:  # R2: every interpolated OCR string is HTML-escaped
        r = it["readings"]
        rows.append(
            f'<div class="item"><h3>{html.escape(it["item_id"])} — PDF page {it["page"]}</h3>'
            f'<img src="{html.escape(it["crop"], quote=True)}">'
            f'<p class="ctx">…{html.escape(it["context"])}…</p>'
            f'<p>baseline: <code>{html.escape(r.get(str(book.baseline), ""))}</code> · '
            f'300: <code>{html.escape(r.get("300", "—"))}</code> · '
            f'360: <code>{html.escape(r.get("360", "—"))}</code></p></div>')
    (qdir / "queue.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Review queue</title>'
        "<style>body{font-family:sans-serif;margin:2em}.item{border-top:1px solid #ccc;"
        "padding:1em 0}img{max-width:100%}.ctx{color:#333}</style>"
        "<h1>Review queue — judge each item against its crop; record decisions with "
        "review_tool decide. Item kinds are concealed until scoring.</h1>" + "".join(rows))
    n_flags = sum(1 for m in mapping.values() if m["kind"] == "flag")
    print(json.dumps({"flags": n_flags, "controls": len(items) - n_flags, "items": len(items),
                      "queue": str(qdir)}, ensure_ascii=False))
    return EXIT_OK


# ---------------------------------------------------------------- decide
def cmd_decide(a) -> int:
    book = Book(a.book_dir, a.pages)
    items = {json.loads(l)["item_id"]: json.loads(l)
             for l in (book.dir / "queue/items.jsonl").read_text().splitlines()}
    if a.item not in items:
        die(EXIT_DECIDE, f"DECIDE_ERROR: unknown item {a.item}")
    if a.decision == "CONFIRM_FIX" and a.corrected is None:
        die(EXIT_DECIDE, "DECIDE_ERROR: CONFIRM_FIX requires an explicit --corrected "
                         "replacement (use --corrected '' for an explicit deletion).")
    log = book.dir / "decisions.jsonl"
    existing = []
    if log.exists():
        existing = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    if any(d["item_id"] == a.item for d in existing):
        die(EXIT_DECIDE, f"DECIDE_ERROR: duplicate decision for {a.item} — rejected (R3).")
    it = items[a.item]
    rec = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "item_id": a.item, "page": it["page"], "decision": a.decision,
           "corrected": a.corrected, "note": a.note or "", "crop": it["crop"],
           "context": it["context"]}
    with log.open("a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False))
    return EXIT_OK


# ----------------------------------------------------------------- apply
def load_decisions(book: Book) -> dict:
    log = book.dir / "decisions.jsonl"
    if not log.exists():
        die(EXIT_APPLY, "APPLY_REFUSED: no decisions.jsonl — review has not started.")
    dec, dup = {}, []
    for l in log.read_text().splitlines():
        if not l.strip():
            continue
        d = json.loads(l)
        if d["item_id"] in dec:
            dup.append(d["item_id"])
        dec[d["item_id"]] = d
    if dup:
        die(EXIT_APPLY, f"APPLY_REFUSED: duplicate decision records for {sorted(set(dup))} (R3).")
    return dec


def cmd_apply(a) -> int:
    book = Book(a.book_dir, a.pages)
    items = {json.loads(l)["item_id"]: json.loads(l)
             for l in (book.dir / "queue/items.jsonl").read_text().splitlines()}
    mapping = json.loads((book.dir / "queue/mapping_sealed.json").read_text())["items"]
    dec = load_decisions(book)
    # Gate 1: completeness — every queue item decided, no unknown IDs.
    missing = sorted(set(items) - set(dec))
    unknown = sorted(set(dec) - set(items))
    if missing or unknown:
        die(EXIT_APPLY, f"APPLY_REFUSED: review incomplete (missing={missing}, unknown={unknown}).")
    # Gate 2: CONFIRM_FIX must carry an explicit replacement.
    bad = [q for q, d in dec.items() if d["decision"] == "CONFIRM_FIX" and d.get("corrected") is None]
    if bad:
        die(EXIT_APPLY, f"APPLY_REFUSED: CONFIRM_FIX without replacement text: {bad} (R3).")
    # Gate 3: source OCR unchanged since queue build (hash check).
    manifest = json.loads((book.dir / "queue/queue_manifest.json").read_text())
    stale = []
    for pg_s, want in manifest["source_ocr_sha256"].items():
        p = book.tier_path(book.baseline, int(pg_s))
        if not p.exists() or sha256(p) != want:
            stale.append(int(pg_s))
    if stale:
        die(EXIT_APPLY, f"APPLY_REFUSED: baseline OCR changed since queue build for pages {stale} (R3).")
    # Gate 4: confirmed-fix spans must not overlap on a page.
    per_page = {}
    for qid, m in mapping.items():
        if m["kind"] == "flag" and dec[qid]["decision"] == "CONFIRM_FIX":
            per_page.setdefault(m["page"], []).append((m["base_span"][0], m["base_span"][1], qid))
    for pg, spans in per_page.items():
        spans.sort()
        for (s1, e1, q1), (s2, e2, q2) in zip(spans, spans[1:]):
            if s2 < e1 or (s1 == e1 == s2 == e2):
                die(EXIT_APPLY, f"APPLY_REFUSED: conflicting fix spans on page {pg}: {q1} [{s1},{e1}) vs {q2} [{s2},{e2}) (R3).")
    # All gates passed — write corrected copies only.
    outdir = book.dir / "corrected"
    outdir.mkdir(exist_ok=True)
    applied = []
    for pg in book.pages:
        s = book.tier_text(book.baseline, pg) if pg not in book.blank_pages else ""
        fixes = sorted([(m["base_span"], dec[qid]["corrected"], qid)
                        for qid, m in mapping.items()
                        if m["kind"] == "flag" and m["page"] == pg and dec[qid]["decision"] == "CONFIRM_FIX"],
                       key=lambda x: -x[0][0])
        for (s0, e0), corr, qid in fixes:
            s = s[:s0] + corr + s[e0:]
            applied.append({"page": pg, "span": [s0, e0], "corrected": corr, "item": qid})
        (outdir / f"p{pg:04d}.txt").write_text(s + "\n")
    print(json.dumps({"applied": len(applied), "detail": applied}, ensure_ascii=False))
    return EXIT_OK


# ----------------------------------------------------------------- score
def map_offset(base: str, gold: str, i: int) -> int:
    sm = difflib.SequenceMatcher(None, base, gold, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if i1 <= i < i2:
            if tag == "equal":
                return j1 + (i - i1)
            return j1
        if tag == "insert" and i1 == i:
            return j1
    return len(gold)


def cmd_score(a) -> int:
    book = Book(a.book_dir, a.pages)
    book.gate_seal()
    book.gate_inputs()
    gold_dir = Path(a.gold_dir) if a.gold_dir else book.gold_dir
    mapping = json.loads((book.dir / "queue/mapping_sealed.json").read_text())["items"]
    decisions = load_decisions(book)
    ts = [d["ts"] for d in decisions.values()]
    review_sec = (datetime.fromisoformat(max(ts)) - datetime.fromisoformat(min(ts))).total_seconds() if ts else 0.0

    def gold(pg):
        return normalize((gold_dir / f"p{pg:04d}.txt").read_text(encoding="utf-8"))

    flags_by_page = {}
    for qid, m in mapping.items():
        if m["kind"] == "flag":
            flags_by_page.setdefault(m["page"], []).append((qid, m))
    tot = {"eb": 0, "ea": 0, "chars": 0, "tp": 0, "fp": 0, "sites": 0, "fn": 0,
           "mech_flags": 0, "mech_sites": 0, "uncertain": 0, "kept_at_error": 0}
    per_page = {}
    for pg in book.pages:
        if pg in book.blank_pages:
            continue
        g, base = gold(pg), book.tier_text(book.baseline, pg)
        corr_path = book.dir / f"corrected/p{pg:04d}.txt"
        if not corr_path.exists():
            die(EXIT_INPUT, f"SCORE_GATE_FAILED: corrected copy missing for page {pg} — run apply first.")
        corr = normalize(corr_path.read_text(encoding="utf-8"))   # normalize BEFORE edit distance
        eb, ea = levenshtein(base, g), levenshtein(corr, g)
        sm = difflib.SequenceMatcher(a=base, b=g, autojunk=False)
        sites = [(i1, i2) for tg, i1, i2, j1, j2 in sm.get_opcodes()
                 if tg != "equal" and (set(base[i1:i2]) & det.PUNCT_SET or set(g[j1:j2]) & det.PUNCT_SET)]
        fl = flags_by_page.get(pg, [])
        tp = fp = mech = unc = kept_err = 0
        fix_cov, flag_cov = set(), set()
        for qid, m in fl:
            s, e = m["base_span"]
            d = decisions.get(qid, {})
            hits = {k for k, (s2, e2) in enumerate(sites) if not (e < s2 - 2 or s > e2 + 2)}
            if hits:
                mech += 1; flag_cov |= hits
            if d.get("decision") == "CONFIRM_FIX" and hits:
                tp += 1; fix_cov |= hits
            elif d.get("decision") == "CONFIRM_FIX":
                fp += 1
            elif d.get("decision") == "UNCERTAIN":
                unc += 1
            elif d.get("decision") == "KEEP" and hits:
                kept_err += 1
        fn = len(sites) - len(fix_cov)
        per_page[str(pg)] = {"edits_before": eb, "edits_after": ea, "gold_chars": len(g),
                             "flags": len(fl), "tp": tp, "fp": fp, "sites": len(sites), "fn": fn,
                             "uncertain": unc, "kept_at_error": kept_err}
        for k, v in (("eb", eb), ("ea", ea), ("chars", len(g)), ("tp", tp), ("fp", fp),
                     ("sites", len(sites)), ("fn", fn), ("mech_flags", mech),
                     ("mech_sites", len(flag_cov)), ("uncertain", unc), ("kept_at_error", kept_err)):
            tot[k] += v
    ctrl = {"items": 0, "confirmed_errors": 0}
    for qid, m in mapping.items():
        if m["kind"] != "control":
            continue
        ctrl["items"] += 1
        d = decisions.get(qid, {})
        if d.get("decision") == "CONFIRM_FIX":
            base = book.tier_text(book.baseline, m["page"])
            g = gold(m["page"])
            j = map_offset(base, g, m["pos"])
            if g[j:j + 1] != base[m["pos"]:m["pos"] + 1]:
                ctrl["confirmed_errors"] += 1
    flags_n = sum(len(v) for v in flags_by_page.values())
    fixes = sum(1 for d in decisions.values() if d["decision"] == "CONFIRM_FIX")
    res = {
        "metric_names": {
            "human_yield": "confirmed valid fixes / reviewed flags (was reported as 'precision' in P16-P18 notes)",
            "mechanical_hit_rate": "flags landing on a census site / flags (span overlap, ignores decisions)",
            "human_coverage": "census sites covered by confirmed fixes / census sites (was 'recall')"},
        "gold_standard": str(gold_dir), "pages": per_page,
        "flags_total": flags_n, "flags_per_page": round(flags_n / max(1, len(book.pages)), 2),
        "true_positives": tot["tp"], "false_positives": tot["fp"],
        "false_negatives": tot["fn"], "true_sites": tot["sites"],
        "human_yield": round(tot["tp"] / flags_n, 4) if flags_n else None,
        "human_coverage": round((tot["sites"] - tot["fn"]) / tot["sites"], 4) if tot["sites"] else None,
        "mechanical_hit_rate": round(tot["mech_flags"] / flags_n, 4) if flags_n else None,
        "mechanical_coverage": round(tot["mech_sites"] / tot["sites"], 4) if tot["sites"] else None,
        "mechanical_covered_sites": tot["mech_sites"],
        "uncertain": tot["uncertain"], "kept_at_error_site": tot["kept_at_error"],
        "edits_before": tot["eb"], "edits_after": tot["ea"], "gold_chars": tot["chars"],
        "cer_before": round(tot["eb"] / tot["chars"], 6), "cer_after": round(tot["ea"] / tot["chars"], 6),
        "review_time_sec": review_sec,
        "review_time_note": "Span between first and last logged decision timestamps. When decisions are "
                            "logged in batches after visual inspection this is a LOWER BOUND on human "
                            "review time, not a stopwatch measurement; no time-savings claim is made.",
        "decisions": len(decisions), "confirmed_fixes": fixes,
        "reviews_per_confirmed_fix": round(flags_n / tot["tp"], 2) if tot["tp"] else None,
        "edits_saved": tot["eb"] - tot["ea"],
        "edits_saved_per_flag_review": round((tot["eb"] - tot["ea"]) / flags_n, 2) if flags_n else None,
        "control_group": {"items": ctrl["items"], "confirmed_errors": ctrl["confirmed_errors"],
                          "hit_rate": round(ctrl["confirmed_errors"] / ctrl["items"], 4) if ctrl["items"] else None},
    }
    (book.dir / "eval_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return EXIT_OK


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("lint", "queue", "decide", "apply", "score"):
        sp = sub.add_parser(name)
        sp.add_argument("--book-dir", required=True)
        sp.add_argument("--pages", help="comma-separated page override, e.g. 72,153,233")
        if name == "decide":
            sp.add_argument("--item", required=True)
            sp.add_argument("--decision", required=True, choices=["CONFIRM_FIX", "KEEP", "UNCERTAIN"])
            sp.add_argument("--corrected", default=None,
                            help="explicit replacement text for CONFIRM_FIX ('' = deletion)")
            sp.add_argument("--note", default="")
        if name == "score":
            sp.add_argument("--gold-dir", default=None, help="defaults to the book's gold dir")
    a = ap.parse_args()
    fn = {"lint": cmd_lint, "queue": cmd_queue, "decide": cmd_decide,
          "apply": cmd_apply, "score": cmd_score}[a.cmd]
    return fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
