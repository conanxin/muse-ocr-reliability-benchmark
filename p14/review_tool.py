#!/usr/bin/env python3
"""review_tool.py -- P18 reusable human-review workflow for OCR punctuation QA.

Subcommands:
  lint   --gold-dir DIR [--seal SEAL.json]
          Reusable gold checks: seal hashes re-verified; ASCII apostrophe
          (U+0027) occurrences in gold produce WARNINGS ONLY (never edited);
          normalize-before-score self-test (P17 erratum rule).
  queue  --book-dir DIR --pages 72,153,... [--seed N]
          Build a blind review queue: frozen P16 detector flags + an equal
          number of random unflagged punctuation controls, shuffled under
          neutral IDs, each with a scan crop and the 200/300/360 readings.
          The flag/control mapping is sealed until decisions are complete.
  decide --book-dir DIR --item Q001 --decision CONFIRM_FIX|KEEP|UNCERTAIN
         [--corrected "..."] [--note "..."]
          Append one timestamped decision (with crop provenance) to the log.
  apply  --book-dir DIR
          Write corrected copies applying ONLY flag items decided
          CONFIRM_FIX. Original OCR files are never modified.
  score  --book-dir DIR --gold-dir DIR
          Dual-track scoring (human decisions vs mechanical spans) plus
          workflow metrics: review time, flags/page, reviews per fix,
          edits saved per review, and the control-group hit rate.

Design rules (from P16/P17): the detector is a black box (imported, never
tuned here); gold is read ONLY by `score` (and `lint`), never by `queue`;
every correction must trace to a logged human decision and a scan crop.
"""
import argparse, csv, difflib, hashlib, io, json, random, subprocess, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "p16"))
from p14 import normalize, levenshtein  # noqa: E402  (canonical, same as detector/scorers use)
import detector as det  # noqa: E402  (frozen P16 detector, do not modify)

PAGES = [72, 153, 233, 314, 395, 475, 556, 637, 718, 798]
PUNCT = set(".,;:!?'\"‘’“”-")
CROP_DPI = 360


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ------------------------------- lint --------------------------------------
def cmd_lint(a):
    ok = True
    if a.seal:
        seal = json.loads(Path(a.seal).read_text())
        for name, want in seal["files"].items():
            got = sha(Path(a.gold_dir) / name)
            print(f"seal {name}: {'OK' if got == want else 'MISMATCH ' + got}")
            ok &= got == want
    warnings = []
    for f in sorted(Path(a.gold_dir).glob("*.txt")):
        t = f.read_text()
        for i, ln in enumerate(t.splitlines(), 1):
            for ch in ln:
                if ch == "'":
                    warnings.append({"file": f.name, "line": i, "context": ln.strip()[:80]})
    print(f"ascii_apostrophe_warnings: {len(warnings)} (WARNING ONLY - inspect the plate;"
          " never auto-replace)")
    for w in warnings:
        print("  WARN", json.dumps(w, ensure_ascii=False))
    # normalize-before-score self-test (P17 erratum): a corrected string with
    # a double space left by a deletion must score identically after the
    # scoring-side normalization.
    g = normalize("the topic. Next")
    raw = "the topic.  Next"  # double space left by an in-memory span deletion
    assert levenshtein(normalize(raw), g) == 0, "normalize-before-score self-test FAILED"
    print("normalize_before_score_selftest: PASS")
    print("LINT_OK" if ok else "LINT_SEAL_MISMATCH")


# ------------------------------- queue -------------------------------------
def tier_text(book, dpi, page):
    return normalize((book / f"work/ocr_{dpi}/p{page:04d}.txt").read_text(errors="replace"))


def map_offset(base, tier, off):
    """Map a char offset in base to the corresponding offset in tier."""
    sm = difflib.SequenceMatcher(a=base, b=tier, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if i1 <= off < i2 or (off == len(base) and i2 == len(base)):
            if tag == "equal":
                return j1 + (off - i1)
            return j1
    return len(tier)


def word_boxes(book, page):
    tsv = book / f"work/tsv/p{page:04d}.tsv"
    words, pos = [], 0
    with open(tsv) as f:
        for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row.get("level") == "5" and row.get("text"):
                w = {"text": row["text"], "left": int(row["left"]), "top": int(row["top"]),
                     "width": int(row["width"]), "height": int(row["height"]), "start": pos}
                pos += len(row["text"]) + 1
                w["end"] = pos - 1
                words.append(w)
    return words


def make_crop(book, page, base_off, tag):
    from PIL import Image
    words = word_boxes(book, page)
    box = None
    for w in words:
        if w["start"] <= base_off < w["end"] or (w["start"] - 3 <= base_off <= w["end"] + 3):
            box = w
            break
    img360 = Image.open(book / f"work/scans_360/p{page:04d}.png")
    scale = CROP_DPI / 200.0
    outdir = book / "queue/crops"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{tag}.png"
    if box is not None:
        cx = (box["left"] + box["width"] / 2) * scale
        cy = (box["top"] + box["height"] / 2) * scale
        hw = max(box["width"] * scale * 4.5, 340)
        hh = max(box["height"] * scale * 2.6, 120)
        method = "tsv_word_box"
    else:
        base = tier_text(book, 200, page)
        frac = base_off / max(1, len(base))
        cx, cy = img360.width / 2, img360.height * frac
        hw, hh = img360.width * 0.46, 130
        method = "fraction_fallback"
    x0, y0 = max(0, int(cx - hw / 2)), max(0, int(cy - hh / 2))
    x1, y1 = min(img360.width, int(cx + hw / 2)), min(img360.height, int(cy + hh / 2))
    img360.crop((x0, y0, x1, y1)).save(out)
    return str(out.relative_to(book)), method


def cmd_queue(a):
    book = Path(a.book_dir)
    seed = a.seed
    flags_all = []
    for pg in PAGES:
        base = tier_text(book, 200, pg)
        f = det.detect(base, tier_text(book, 300, pg), tier_text(book, 360, pg))
        for fl in f:
            fl["page"] = pg
        flags_all.extend(f)
    rng = random.Random(seed)
    controls = []
    for pg in PAGES:
        base = tier_text(book, 200, pg)
        spans = [(fl["base_span"][0], fl["base_span"][1]) for fl in flags_all if fl["page"] == pg]
        cand = [i for i, c in enumerate(base)
                if c in PUNCT and all(not (s - 2 <= i <= e + 2) for s, e in spans)]
        nf = sum(1 for fl in flags_all if fl["page"] == pg)
        pick = rng.sample(cand, min(nf, len(cand))) if cand else []
        for i in pick:
            controls.append({"page": pg, "pos": i, "char": base[i]})
    items, mapping = [], {}
    pool = ([{"kind": "flag", "ref": fl} for fl in flags_all] +
            [{"kind": "control", "ref": c} for c in controls])
    rng.shuffle(pool)
    for n, entry in enumerate(pool, 1):
        qid = f"Q{n:03d}"
        if entry["kind"] == "flag":
            fl = entry["ref"]
            pg, (s, e) = fl["page"], fl["base_span"]
            base = tier_text(book, 200, pg)
            pos = sorted(fl["positions"], key=lambda p: p["base_index"])

            def rd(key):
                return "".join(p[key] if p[key] is not None else "∅" for p in pos)
            item = {"item_id": qid, "page": pg, "base_span": [s, e],
                    "context": base[max(0, s - 45):e + 45],
                    "readings": {"200": base[s:e], "300": rd("reading_300"), "360": rd("reading_360")},
                    "category": "punct_disagreement", "base_text": fl["base_text"]}
            mapping[qid] = {"kind": "flag", "page": pg, "base_span": [s, e],
                            "category": "punct_disagreement", "base_text": fl["base_text"]}
            crop_off = s
        else:
            c = entry["ref"]
            pg, i = c["page"], c["pos"]
            base = tier_text(book, 200, pg)
            t300, t360 = tier_text(book, 300, pg), tier_text(book, 360, pg)
            j3, j6 = map_offset(base, t300, i), map_offset(base, t360, i)
            item = {"item_id": qid, "page": pg, "base_span": [i, i + 1],
                    "context": base[max(0, i - 45):i + 46],
                    "readings": {"200": base[i:i + 1],
                                 "300": t300[j3:j3 + 1], "360": t360[j6:j6 + 1]},
                    "category": "punct_site"}
            mapping[qid] = {"kind": "control", "page": pg, "pos": i, "char": c["char"]}
            crop_off = i
        crop, method = make_crop(book, pg, crop_off, qid)
        item["crop"] = crop
        item["crop_method"] = method
        mapping[qid]["crop"] = crop
        items.append(item)
    qdir = book / "queue"
    qdir.mkdir(exist_ok=True)
    (qdir / "items.jsonl").write_text("".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items))
    (qdir / "mapping_sealed.json").write_text(json.dumps(
        {"sealed_at": now(), "seed": seed, "note": "DO NOT OPEN until all decisions are logged.",
         "items": mapping}, indent=1, ensure_ascii=False) + "\n")
    rows = []
    for it in items:
        rows.append(f"""<div class="item"><h3>{it['item_id']} &middot; PDF p.{it['page']}</h3>
<img src="{it['crop']}" alt="crop">
<p class="ctx">{it['context']}</p>
<p>200: <code>{it['readings']['200']}</code> &nbsp; 300: <code>{it['readings']['300']}</code> &nbsp; 360: <code>{it['readings']['360']}</code></p>
<p>Decision: CONFIRM_FIX / KEEP / UNCERTAIN &mdash; record with <code>review_tool.py decide</code></p></div>""")
    (qdir / "queue.html").write_text(
        "<!DOCTYPE html><meta charset='utf-8'><title>OCR review queue</title>"
        "<style>body{font-family:system-ui;max-width:820px;margin:2em auto}"
        ".item{border:1px solid #ccc;padding:1em;margin:1em 0}.ctx{background:#f6f6f6;padding:.5em}"
        "img{max-width:100%}</style><h1>Review queue (blind: flags + random controls)</h1>" + "\n".join(rows))
    print(json.dumps({"flags": len(flags_all), "controls": len(controls),
                      "items": len(items), "queue": str(qdir)}, ensure_ascii=False))


# ------------------------------- decide ------------------------------------
def cmd_decide(a):
    book = Path(a.book_dir)
    items = {json.loads(l)["item_id"]: json.loads(l)
             for l in (book / "queue/items.jsonl").read_text().splitlines()}
    it = items[a.item]
    rec = {"ts": now(), "item_id": a.item, "page": it["page"], "decision": a.decision,
           "crop": it["crop"], "crop_method": it["crop_method"]}
    if a.corrected is not None:
        rec["corrected"] = a.corrected
    if a.note:
        rec["note"] = a.note
    with open(book / "decisions.jsonl", "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False))


# ------------------------------- apply -------------------------------------
def cmd_apply(a):
    book = Path(a.book_dir)
    mapping = json.loads((book / "queue/mapping_sealed.json").read_text())["items"]
    decisions = {}
    for l in (book / "decisions.jsonl").read_text().splitlines():
        d = json.loads(l)
        decisions[d["item_id"]] = d
    fixes = {}
    for qid, m in mapping.items():
        d = decisions.get(qid)
        if m["kind"] == "flag" and d and d["decision"] == "CONFIRM_FIX" and "corrected" in d:
            fixes.setdefault(m["page"], []).append((m["base_span"], d["corrected"], qid))
    outdir = book / "corrected"
    outdir.mkdir(exist_ok=True)
    applied = []
    for pg in PAGES:
        base = tier_text(book, 200, pg)
        s = base
        for (sp, corr, qid) in sorted(fixes.get(pg, []), key=lambda x: -x[0][0]):
            s = s[:sp[0]] + corr + s[sp[1]:]
            applied.append({"page": pg, "span": sp, "corrected": corr, "item": qid})
        (outdir / f"p{pg:04d}.txt").write_text(s + "\n")
    print(json.dumps({"applied": len(applied), "detail": applied}, ensure_ascii=False))


# ------------------------------- score -------------------------------------
def cmd_score(a):
    book = Path(a.book_dir)
    gold_dir = Path(a.gold_dir)
    mapping = json.loads((book / "queue/mapping_sealed.json").read_text())["items"]
    decisions = {}
    for l in (book / "decisions.jsonl").read_text().splitlines():
        d = json.loads(l)
        decisions[d["item_id"]] = d
    ts = [json.loads(l)["ts"] for l in (book / "decisions.jsonl").read_text().splitlines()]
    t0, t1 = datetime.fromisoformat(ts[0]), datetime.fromisoformat(ts[-1])
    review_sec = (t1 - t0).total_seconds()

    def gold(pg):
        return normalize((gold_dir / f"p{pg:04d}.txt").read_text())

    # census of true punctuation error sites (same method as P16/P17)
    flags_by_page = {}
    for qid, m in mapping.items():
        if m["kind"] == "flag":
            flags_by_page.setdefault(m["page"], []).append((qid, m))
    tot = {"eb": 0, "ea": 0, "chars": 0, "tp": 0, "fp": 0, "sites": 0, "fn": 0,
           "mech_flags": 0, "mech_sites": 0, "uncertain": 0, "kept_at_error": 0}
    per_page = {}
    ctrl = {"n": 0, "confirmed_errors": 0}
    for pg in PAGES:
        g, base = gold(pg), tier_text(book, 200, pg)
        corr = normalize((book / f"corrected/p{pg:04d}.txt").read_text())
        eb, ea = levenshtein(base, g), levenshtein(corr, g)
        sm = difflib.SequenceMatcher(a=base, b=g, autojunk=False)
        sites = []
        for tg, i1, i2, j1, j2 in sm.get_opcodes():
            if tg == "equal":
                continue
            if set(base[i1:i2]) & det.PUNCT_SET or set(g[j1:j2]) & det.PUNCT_SET:
                sites.append((i1, i2))
        fl = flags_by_page.get(pg, [])
        tp = fp = mech = unc = kept_err = 0
        fix_covered, flag_covered = set(), set()
        for qid, m in fl:
            s, e = m["base_span"]
            d = decisions.get(qid, {})
            hits = {k for k, (s2, e2) in enumerate(sites) if not (e < s2 - 2 or s > e2 + 2)}
            at_site = bool(hits)
            if at_site:
                mech += 1
                flag_covered |= hits
            if d.get("decision") == "CONFIRM_FIX" and at_site:
                tp += 1
                fix_covered |= hits
            elif d.get("decision") == "CONFIRM_FIX":
                fp += 1
            elif d.get("decision") == "UNCERTAIN":
                unc += 1
            elif d.get("decision") == "KEEP" and at_site:
                kept_err += 1
        fn = len(sites) - len(fix_covered)
        per_page[str(pg)] = {"edits_before": eb, "edits_after": ea, "gold_chars": len(g),
                             "flags": len(fl), "tp": tp, "fp": fp, "sites": len(sites), "fn": fn,
                             "uncertain": unc, "kept_at_error": kept_err}
        for k, v in (("eb", eb), ("ea", ea), ("chars", len(g)), ("tp", tp), ("fp", fp),
                     ("sites", len(sites)), ("fn", fn), ("mech_flags", mech),
                     ("mech_sites", len(flag_covered)), ("uncertain", unc),
                     ("kept_at_error", kept_err)):
            tot[k] += v
    for qid, m in mapping.items():
        if m["kind"] != "control":
            continue
        d = decisions.get(qid, {})
        ctrl["n"] += 1
        if d.get("decision") == "CONFIRM_FIX":
            g = gold(m["page"])
            i = m["pos"]
            base = tier_text(book, 200, m["page"])
            # verify against gold via alignment: control char correct iff the
            # aligned gold char equals the base char
            j = map_offset(base, g, i)
            if g[j:j + 1] != base[i:i + 1]:
                ctrl["confirmed_errors"] += 1
    flags_n = sum(len(v) for v in flags_by_page.values())
    res = {
        "gold_standard": str(gold_dir),
        "pages": per_page,
        "flags_total": flags_n, "flags_per_page": round(flags_n / len(PAGES), 2),
        "true_positives": tot["tp"], "false_positives": tot["fp"],
        "false_negatives": tot["fn"], "true_sites": tot["sites"],
        "precision": round(tot["tp"] / flags_n, 4) if flags_n else None,
        "recall": round((tot["sites"] - tot["fn"]) / tot["sites"], 4) if tot["sites"] else None,
        "mechanical_precision": round(tot["mech_flags"] / flags_n, 4) if flags_n else None,
        "mechanical_recall": round(tot["mech_sites"] / tot["sites"], 4) if tot["sites"] else None,
        "mechanical_covered_sites": tot["mech_sites"],
        "uncertain": tot["uncertain"], "kept_at_error_site": tot["kept_at_error"],
        "edits_before": tot["eb"], "edits_after": tot["ea"], "gold_chars": tot["chars"],
        "cer_before": round(tot["eb"] / tot["chars"], 6), "cer_after": round(tot["ea"] / tot["chars"], 6),
        "review_time_sec": review_sec, "decisions": len(decisions),
        "seconds_per_item": round(review_sec / max(1, len(decisions)), 1),
        "reviews_per_confirmed_fix": round(flags_n / tot["tp"], 2) if tot["tp"] else None,
        "edits_saved": tot["eb"] - tot["ea"],
        "edits_saved_per_flag_review": round((tot["eb"] - tot["ea"]) / flags_n, 3) if flags_n else None,
        "control_group": {"items": ctrl["n"], "confirmed_errors": ctrl["confirmed_errors"],
                          "hit_rate": round(ctrl["confirmed_errors"] / ctrl["n"], 4) if ctrl["n"] else None},
    }
    (book / "eval_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(res, indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lint"); p.add_argument("--gold-dir", required=True); p.add_argument("--seal")
    p.set_defaults(fn=cmd_lint)
    p = sub.add_parser("queue"); p.add_argument("--book-dir", required=True); p.add_argument("--seed", type=int, default=20261023)
    p.set_defaults(fn=cmd_queue)
    p = sub.add_parser("decide"); p.add_argument("--book-dir", required=True); p.add_argument("--item", required=True)
    p.add_argument("--decision", required=True, choices=["CONFIRM_FIX", "KEEP", "UNCERTAIN"])
    p.add_argument("--corrected"); p.add_argument("--note"); p.set_defaults(fn=cmd_decide)
    p = sub.add_parser("apply"); p.add_argument("--book-dir", required=True); p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("score"); p.add_argument("--book-dir", required=True); p.add_argument("--gold-dir", required=True)
    p.set_defaults(fn=cmd_score)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
