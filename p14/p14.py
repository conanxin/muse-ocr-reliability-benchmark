#!/usr/bin/env python3
"""P14 independent-book OCR pilot. Standard library + Poppler + Tesseract."""
import argparse
import collections
import hashlib
import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'manifest.json'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as inp:
        while True:
            piece = inp.read(2**20)
            if not piece: break
            h.update(piece)
    return h.hexdigest()


def run(*argv, timeout=180):
    p = subprocess.run(argv, capture_output=True, text=True, errors='replace', timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"Failed {argv[0]} exit={p.returncode}: {p.stderr[-1200:]}")
    return p.stdout


def need(*programs):
    absent = [p for p in programs if shutil.which(p) is None]
    if absent: raise RuntimeError('Missing executables: ' + ', '.join(absent))


def protocol():
    m = read_json(MANIFEST)
    pages = m['pages_pdf_1based']
    gold = m['blind_gold_pages_pdf_1based']
    if len(pages) != 20 or len(pages) != len(set(pages)):
        raise ValueError('Requires 20 unique preselected PDF pages')
    if set(gold) - set(pages) or len(gold) != 5:
        raise ValueError('Requires 5 blind-gold pages within the selected 20')
    return m, pages, gold


def name(page): return f'p{page:04d}'


def prepare(pdf, out):
    need('pdfinfo', 'pdftoppm', 'pdfimages')
    m, pages, gold = protocol()
    pdf = Path(pdf).expanduser().resolve()
    if not pdf.is_file(): raise FileNotFoundError(pdf)
    with pdf.open('rb') as f:
        if f.read(5) != b'%PDF-': raise ValueError('Not a PDF')
    info = run('pdfinfo', str(pdf), timeout=45)
    n = re.search(r'(?m)^Pages:\s*(\d+)', info)
    if not n: raise RuntimeError('Cannot identify PDF page count')
    count = int(n.group(1))
    expected = m['source']['pdf_pages_expected']
    if count != expected:
        raise RuntimeError(f'PDF edition mismatch: expected {expected}, found {count}; do not reuse page numbers')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lock = out/'page_selection.json'
    lockval = dict(pdf_path=str(pdf), pdf_sha256=digest(pdf), pages=pages,
                   blind_gold_pages=gold, manifest_sha256=digest(MANIFEST),
                   render_dpi=200, render_dpi_is_not_native_ppi=True)
    if lock.exists() and read_json(lock) != lockval:
        raise RuntimeError('PRE-REGISTERED SELECTION MISMATCH; refusing overwrite')
    if not lock.exists(): write_json(lock, lockval)
    for sub in ['scans', 'ocr', 'gold', 'native_inventory']:
        (out/sub).mkdir(exist_ok=True)
    results = []
    for page in pages:
        base = name(page)
        image = out/'scans'/(base+'.png')
        if not image.exists():
            run('pdftoppm','-f',str(page),'-l',str(page),'-r','200','-gray','-png',
                '-singlefile',str(pdf),str(out/'scans'/base),timeout=180)
        inv = run('pdfimages','-f',str(page),'-l',str(page),'-list',str(pdf),timeout=45)
        (out/'native_inventory'/(base+'.txt')).write_text(inv, encoding='utf-8')
        results.append({'pdf_page':page,'rendered_image':str(image),
                        'rendered_sha256':digest(image),
                        'native_inventory':str(out/'native_inventory'/(base+'.txt'))})
        print(f'PREPARED p.{page}: {image.name}')
    write_json(out/'scan_preflight.json',{'status':'PREPARED', 'pdf_sha256':digest(pdf),
                                          'pdf_pages':count, 'pages':results})
    print('MANUAL_GOLD_REQUIRED: PDF pages',gold)
    print('Do NOT use OCR text to compose ground truth. Only scans/ and source PDF.')


def ocr(out):
    need('tesseract')
    m, pages, gold = protocol()
    out = Path(out)
    selected = read_json(out/'page_selection.json')
    if selected['manifest_sha256'] != digest(MANIFEST):
        raise RuntimeError('Protocol edited after preregistration')
    language_output = run('tesseract','--list-langs',timeout=30)
    if 'eng' not in language_output.split():
        raise RuntimeError('Missing Tesseract eng traineddata')
    missing_gold = [p for p in gold if not (out/'gold'/(name(p)+'.txt')).is_file()]
    if missing_gold:
        raise RuntimeError(f'Blind gold not sealed. Missing transcriptions for pages: {missing_gold}')
    seal = {str(p):digest(out/'gold'/(name(p)+'.txt')) for p in gold}
    sealpath = out/'gold_seal.json'
    if sealpath.exists() and read_json(sealpath) != seal:
        raise RuntimeError('Gold changed after seal; log adjudication before rerunning')
    if not sealpath.exists(): write_json(sealpath,seal)
    for p in pages:
        scan = out/'scans'/(name(p)+'.png')
        if not scan.exists(): raise FileNotFoundError(scan)
        outfile = out/'ocr'/(name(p)+'.txt')
        if not outfile.exists():
            # Capture as bytes to preserve UTF-8 regardless of Windows console encoding.
            proc = subprocess.run(['tesseract',str(scan),'stdout','-l','eng','--psm','3'],
                                  capture_output=True,timeout=180)
            if proc.returncode:
                raise RuntimeError(f'Tesseract p.{p} exit={proc.returncode}: {proc.stderr[-200:]}')
            outfile.write_bytes(proc.stdout)
        print('OCR_COMPLETE',p, 'bytes=',outfile.stat().st_size)
    write_json(out/'ocr_receipt.json',{'status':'OCR_COMPLETE','pages':pages,
                                     'ocr_file_sha256':{str(p):digest(out/'ocr'/(name(p)+'.txt')) for p in pages},
                                     'gold_seal':seal,'language':'eng','psm':3})


def normalize(s):
    """NFC + collapse whitespace only; preserve punctuation and case."""
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', s)).strip()


def levenshtein(a, b):
    if len(a) < len(b): a, b = b, a
    previous = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1]+1, previous[j]+1,
                               previous[j-1]+(ca != cb)))
        previous = current
    return previous[-1]


def words(s):
    return re.findall(r"[A-Za-z]+(?:[-'’][A-Za-z]+)*|\d+(?:[.,]\d+)*", s)


def optional_labels(path, kind):
    path = Path(path)
    if not path.exists(): return {'status':'NOT_MEASURED', 'reason':'manual labels absent'}
    records = [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    if kind == 'omissions':
        verified = [x for x in records if x.get('source_verified') is True]
        if not verified: return {'status':'NOT_MEASURED', 'reason':'no source-verified omission units'}
        if any(type(x.get('detected_by_ocr_quality_gate')) is not bool for x in verified):
            raise ValueError('Every verified omission label needs boolean detected_by_ocr_quality_gate')
        tp = sum(x['detected_by_ocr_quality_gate'] for x in verified)
        return {'status':'MEASURED', 'verified_omission_units':len(verified),
                'true_positives':tp,'false_negatives':len(verified)-tp,
                'recall':tp/len(verified)}
    if kind == 'ai':
        verified = [x for x in records if x.get('gold_checked') is True]
        allowed = {'correct_applied','miscorrection_applied','proposed_wrong_rejected'}
        if any(x.get('human_verdict') not in allowed for x in verified):
            raise ValueError('AI labels must use correct_applied/miscorrection_applied/proposed_wrong_rejected')
        applied = [x for x in verified if x['human_verdict'].endswith('_applied')]
        rejected = sum(x['human_verdict']=='proposed_wrong_rejected' for x in verified)
        if not applied: return {'status':'NOT_MEASURED','reason':'no gold-reviewed applied edits',
                                'wrong_proposals_rejected':rejected}
        bad = sum(x['human_verdict']=='miscorrection_applied' for x in applied)
        return {'status':'MEASURED', 'applied_edits_reviewed':len(applied),
                'applied_miscorrections':bad,'miscorrection_rate':bad/len(applied),
                'wrong_proposals_rejected':rejected}
    raise ValueError(kind)


def score(out):
    m, pages, gold = protocol()
    out = Path(out)
    lock = read_json(out/'page_selection.json')
    if lock['manifest_sha256'] != digest(MANIFEST):
        raise RuntimeError('Protocol changed after page selection')
    if set(lock['pages']) != set(pages):
        raise RuntimeError('Page selection drift')
    ocr_receipt = read_json(out/'ocr_receipt.json')
    if ocr_receipt['pages'] != pages:
        raise RuntimeError('OCR receipt does not match preregistration')
    seal = read_json(out/'gold_seal.json')
    if any(str(p) not in seal or seal[str(p)] != digest(out/'gold'/(name(p)+'.txt')) for p in gold):
        raise RuntimeError('Blind-gold file has changed after seal')
    for p in pages:
        path = out/'ocr'/(name(p)+'.txt')
        if not path.exists() or digest(path) != ocr_receipt['ocr_file_sha256'].get(str(p)):
            raise RuntimeError(f'OCR file missing or changed for PDF p.{p}')
    totals = {'char_edits':0,'gold_chars':0,'word_edits':0,'gold_words':0}
    per_page = []
    for p in pages:
        if p not in gold:
            per_page.append({'pdf_page':p,'status':'NOT_MEASURED','reason':'no preregistered blind-gold'})
            continue
        gt = normalize((out/'gold'/(name(p)+'.txt')).read_text(encoding='utf-8'))
        pred = normalize((out/'ocr'/(name(p)+'.txt')).read_text(encoding='utf-8'))
        if not gt:
            per_page.append({'pdf_page':p,'status':'NOT_MEASURED','reason':'gold empty'})
            continue
        cd = levenshtein(pred,gt)
        gw = words(gt); pw = words(pred)
        wd = levenshtein(pw,gw) if gw else None
        totals['char_edits'] += cd; totals['gold_chars'] += len(gt)
        if wd is not None:
            totals['word_edits'] += wd; totals['gold_words'] += len(gw)
        per_page.append({'pdf_page':p,'status':'MEASURED', 'gold_chars':len(gt),
                         'char_edits':cd, 'strict_CER':cd/len(gt),
                         'gold_words':len(gw),'word_edits':wd,
                         'WER':wd/len(gw) if gw else None})
    sample_count = sum(x['status']=='MEASURED' for x in per_page)
    c = totals['char_edits']/totals['gold_chars'] if totals['gold_chars'] else None
    w = totals['word_edits']/totals['gold_words'] if totals['gold_words'] else None
    result = {'status':'SAMPLED_MEASUREMENT' if sample_count==len(gold) else 'PARTIAL_ONLY',
              'book':'The Chinese Recorder and Missionary Journal, Vol. 27 (1896)',
              'pages_ocr_total':len(pages),'blind_gold_target':len(gold),
              'blind_gold_measured':sample_count,'strict_CER_sample':c,'WER_sample':w,
              'total_char_edits':totals['char_edits'],'total_gold_chars':totals['gold_chars'],
              'total_word_edits':totals['word_edits'],'total_gold_words':totals['gold_words'],
              'omission_recall':optional_labels(out/'omission_labels.jsonl','omissions'),
              'ai_miscorrection':optional_labels(out/'ai_decisions.jsonl','ai'),
              'page_details':per_page,
              'caveat':'A 5-page subset of one independent English historical volume; not broad generalization.'}
    write_json(out/'score.json',result)
    print(json.dumps({k:v for k,v in result.items() if k != 'page_details'},ensure_ascii=False,indent=2))
    return 0 if sample_count==len(gold) else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('prepare'); a.add_argument('--pdf',required=True); a.add_argument('--out',required=True)
    a=sub.add_parser('ocr'); a.add_argument('--out',required=True)
    a=sub.add_parser('score'); a.add_argument('--out',required=True)
    args=parser.parse_args()
    if args.mode=='prepare': prepare(args.pdf,args.out)
    elif args.mode=='ocr': ocr(args.out)
    else: return score(args.out)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
