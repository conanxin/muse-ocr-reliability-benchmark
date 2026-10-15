#!/usr/bin/env python3
"""
P11 OCR Reliability Benchmark - Case Generator
从 corrections.json、gap_insertions.json 生成评测案例，提取原生分辨率裁图。
"""
import json, os, re
from pathlib import Path
from PIL import Image

BASE = Path(__file__).parent.parent
BENCH = Path(__file__).parent
IMAGES = BENCH / "images"
NATIVE_DIR = BASE / "audit_p82"  # native-XXX.png (199 PPI)
PAGES_DIR = BASE / "pages"  # page-XXXX.json (300 DPI bboxes)
SCALE = 0.6623  # 300 DPI -> 199 PPI

def find_text_location(pdf_page, search_text, pages_cache):
    """在 pages/page-XXXX.json 中定位文本，返回 bboxes"""
    if pdf_page not in pages_cache:
        pfile = PAGES_DIR / f"page-{pdf_page:04d}.json"
        if not pfile.exists():
            return []
        pages_cache[pdf_page] = json.load(open(pfile))
    lines = pages_cache[pdf_page].get('lines', [])
    # 找包含 search_text（或其子串）的行
    hits = []
    # 用 original 的前 10 个字符搜索
    key = search_text[:12].strip()
    for i, ln in enumerate(lines):
        if key and key in ln['text']:
            hits.append((i, ln))
    return hits

def crop_native(pdf_page, bboxes_300dpi, case_id, pad=30):
    """从原生图裁切，返回图像路径"""
    nfile = NATIVE_DIR / f"native-{pdf_page-1:03d}.png"
    if not nfile.exists():
        return None
    im = Image.open(nfile)
    # 合并 bboxes
    x0 = min(b[0] for b in bboxes_300dpi) - pad
    y0 = min(b[1] for b in bboxes_300dpi) - pad
    x1 = max(b[2] for b in bboxes_300dpi) + pad
    y1 = max(b[3] for b in bboxes_300dpi) + pad
    # 转原生坐标
    x0, y0, x1, y1 = [int(v * SCALE) for v in (x0, y0, x1, y1)]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(im.width, x1), min(im.height, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = im.crop((x0, y0, x1, y1))
    # 放大 1.5x 便于查看（NEAREST 保持像素真实）
    crop = crop.resize((int(crop.width*1.5), int(crop.height*1.5)), Image.NEAREST)
    out = IMAGES / f"{case_id}.png"
    crop.save(out)
    return str(out.relative_to(BENCH))

def main():
    IMAGES.mkdir(parents=True, exist_ok=True)
    corr = json.load(open(BASE / "corrections.json"))
    gaps = json.load(open(BASE / "gap_insertions.json"))
    pages_cache = {}
    cases = []
    
    # === Subset 1: OCR (OCR 引擎错误) ===
    # 1a. confirmed corrections (OCR 误识 -> 真值)
    ocr_id = 0
    for c in corr:
        if c.get('status') != 'confirmed':
            continue
        ocr_id += 1
        cid = f"OCR-{ocr_id:03d}"
        pg = c['pdf_page']
        orig = c['original']
        # 定位
        hits = find_text_location(pg, orig, pages_cache)
        img_path = None
        bbox = None
        if hits:
            bboxes = [ln['bbox'] for _, ln in hits[:3]]  # 最多 3 行
            bbox = [min(b[0] for b in bboxes), min(b[1] for b in bboxes),
                    max(b[2] for b in bboxes), max(b[3] for b in bboxes)]
            img_path = crop_native(pg, bboxes, cid)
        # 错误类别
        cat = categorize_ocr_error(orig, c['corrected'])
        cases.append({
            "case_id": cid,
            "subset": "ocr",
            "pdf_page": pg,
            "bbox_300dpi": bbox,
            "image": img_path,
            "ocr_text": orig,
            "ground_truth": c['corrected'],
            "error_category": cat,
            "history_chain": [{
                "patch_id": c.get('patch_id'),
                "status": c.get('status'),
                "basis": c.get('basis'),
            }],
            "source": f"corrections.json#{c.get('patch_id') or 'P6/P7'}",
        })
    
    # 1b. gap insertions (整行/整句漏文)
    for i, g in enumerate(gaps, 1):
        cid = f"OCR-GAP-{i:02d}"
        pg = g['pdf_page']
        # 用 'after' 定位间隙
        hits = find_text_location(pg, g['after'][:20], pages_cache)
        img_path = None
        bbox = None
        if hits:
            # 裁切间隙区域（after 行下方）
            ln = hits[0][1]
            b = ln['bbox']
            gap_box = [[b[0], b[3], b[2], b[3]+120]]  # 下方 120px
            bbox = gap_box[0]
            img_path = crop_native(pg, gap_box, cid, pad=20)
        cases.append({
            "case_id": cid,
            "subset": "ocr",
            "pdf_page": pg,
            "bbox_300dpi": bbox,
            "image": img_path,
            "ocr_text": "",  # 漏文：OCR 输出为空
            "ground_truth": g['insert'],
            "error_category": "omission_line",
            "history_chain": [{"basis": g.get('basis')}],
            "source": f"gap_insertions.json#{i}",
        })
    
    # === Subset 2: AI_CORRECTION (AI 校正决策) ===
    ai_id = 0
    for c in corr:
        ai_id += 1
        cid = f"AI-{ai_id:03d}"
        # verdict: AI 的校正是否正确
        verdict = "correct" if c.get('status') == 'confirmed' else "incorrect"
        if c.get('status') == 'rejected':
            verdict = "incorrect"  # 被驳回的提议
        cases.append({
            "case_id": cid,
            "subset": "ai_correction",
            "pdf_page": c['pdf_page'],
            "bbox_300dpi": None,  # AI 决策案例不强制配图（图像在 OCR 子集）
            "image": None,
            "ocr_text": c['original'],  # AI 看到的输入
            "ground_truth": c['corrected'] if verdict == "correct" else c['original'],
            "ai_proposed": c['corrected'],
            "verdict": verdict,
            "error_category": "ai_miscorrection" if verdict == "incorrect" else "ai_correct",
            "history_chain": [{
                "patch_id": c.get('patch_id'),
                "status": c.get('status'),
                "basis": c.get('basis'),
                "revert_reason": c.get('revert_reason'),
            }],
            "source": f"corrections.json#{c.get('patch_id') or 'P6/P7'}",
        })
    
    # === Subset 3: NOTION_PUBLISH ===
    # P9 同步验证案例（本地 vs Notion 一致性）
    # 从 manifest 的 p9_release 取 15 项
    mf = json.load(open(BASE / "manifest.json"))
    p9 = mf.get('p9_release', {})
    for i, pid in enumerate(p9.get('patch_ids', []), 1):
        cid = f"NOTION-{i:02d}"
        # 找对应 correction
        c = next((x for x in corr if x.get('patch_id') == pid), None)
        if not c:
            continue
        cases.append({
            "case_id": cid,
            "subset": "notion_publish",
            "pdf_page": c['pdf_page'],
            "bbox_300dpi": None,
            "image": None,
            "ocr_text": c['original'],
            "ground_truth": c['corrected'],
            "error_category": "sync_verification",
            "history_chain": [{"patch_id": pid, "source": "P9 Notion 在线修复回同步"}],
            "source": f"manifest.json#p9_release#{pid}",
        })
    
    # 写 cases.jsonl
    with open(BENCH / "cases.jsonl", 'w', encoding='utf-8') as f:
        for cs in cases:
            f.write(json.dumps(cs, ensure_ascii=False) + '\n')
    
    # 统计
    from collections import Counter
    print(f"总案例: {len(cases)}")
    print(f"子集分布: {Counter(c['subset'] for c in cases)}")
    with_img = sum(1 for c in cases if c['image'])
    print(f"有图像: {with_img} ({with_img/len(cases)*100:.1f}%)")

def categorize_ocr_error(orig, corr):
    """简单错误分类"""
    if len(orig) == 0 or len(corr) == 0:
        return "omission" if len(orig) < len(corr) else "insertion"
    if len(orig) != len(corr):
        # 长度不同：可能是漏字/多字
        if abs(len(orig) - len(corr)) <= 2:
            return "char_substitution"
        return "omission_fragment" if len(orig) < len(corr) else "insertion_fragment"
    # 等长：字符替换
    diffs = sum(1 for a, b in zip(orig, corr) if a != b)
    if diffs == 1:
        return "char_substitution"
    return "multi_char_error"

if __name__ == '__main__':
    main()
