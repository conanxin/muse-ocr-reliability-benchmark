# Muse OCR Reliability Benchmark v0.1.0 (Public Candidate)

**状态：** 发布候选（未正式发布）
**建议仓库：** `conanxin/muse-ocr-reliability-benchmark`
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

433 案例 + 384 原生图像暂不包含在本候选包，随 v1.0 发布。

## 重要声明

本数据集来自同一本书，不得作为泛化成绩。详见 METRICS.md。
