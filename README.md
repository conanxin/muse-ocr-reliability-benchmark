# Muse OCR Reliability Benchmark

**状态：** [v0.1.0 Research Beta · Pre-release](https://github.com/conanxin/muse-ocr-reliability-benchmark/releases/tag/v0.1.0)（2026-10-15 已发布）
**仓库：** [conanxin/muse-ocr-reliability-benchmark](https://github.com/conanxin/muse-ocr-reliability-benchmark)
**许可：** MIT（代码）

## 包含内容

| 文件 | 说明 |
|------|------|
| `demo_cases.jsonl` | 12 条已验证演示案例 |
| `eval.py` | 评测脚本 |
| `generate_cases.py` | 案例生成脚本（需完整项目目录） |
| `METRICS.md` | 指标定义与基线 |
| `CHANGELOG.md` | 版本历史 |

## 快速开始

```bash
# 运行评测（需 cases.jsonl，演示包用 demo_cases.jsonl 代替）
cp demo_cases.jsonl cases.jsonl
python3 eval.py
python3 eval.py --test-known-failures
```

### Windows PowerShell

```powershell
git clone https://github.com/conanxin/muse-ocr-reliability-benchmark.git
cd muse-ocr-reliability-benchmark
Copy-Item demo_cases.jsonl cases.jsonl
python eval.py
python eval.py --test-known-failures
```

**Tag 与 main 的区别：** v0.1.0 Tag 固定在提交 `b6754c3f903955fa00629696bd7f309188f84edf`；main 包含发布后的 README 和控制台兼容性修复。原始 Tag 在 Windows GBK 终端出现 `UnicodeEncodeError` 时，可以先运行 `$env:PYTHONIOENCODING = 'utf-8'`。

## 案例 Schema

见 `demo_cases.jsonl` 首行。字段：
- `case_id`：唯一标识（如 OCR-160）
- `subset`：ocr | ai_correction | notion_publish
- `pdf_page`、`bbox_300dpi`：来源位置
- `image`：图像路径（演示包不含文件）
- `ocr_text`、`ground_truth`：OCR 输出与真值
- `error_category`：错误类别
- `history_chain`：校正历史
- `source`：数据来源

## 完整数据

完整研究集有 **433 个案例**，其中 **384 个案例含原生图像证据（202 个不同图像文件）**。公开仓库只包含 12 条文本演示案例，不含原始 PDF 或裁图。是否进一步开放完整数据集另行决定。

## 重要声明

本数据集来自同一本书，不得作为泛化成绩。公开演示案例 CER 与私有完整错误案例集的历史 CER 不同，不能混用。详见 [METRICS.md](METRICS.md)。
