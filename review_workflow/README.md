# Review-Assisted OCR QA Workflow — v0.2.0 Research Beta

**定位（唯一允许的宣称）**：人机协同的 OCR 质量复核研究原型。它用三个 DPI 档位的 OCR
读数分歧提出标点疑点，展示原图裁图，由人工逐条判定，只把明确批准的修订写入副本。
在一本十页的第三本书测试中，人工复核把 CER 从 1.0744% 降至 0.9661%。疑点覆盖率随
语料显著变化（P16 85.2%、P17 87.5%、P18 37.1%），使用者必须复核全部建议。

**不得宣称**：自动标点纠错；无语料限定的「87% 召回率」；适用于所有历史书籍；
「人工每条只需 2.9 秒」；「严格双盲对照」；「已测得人工耗时节省」。

本包由 P14–P18 研究阶段固化而来（研究档案在 `experiment/p14-crossbook-1896` 分支，
不在本发布包内）。检测器算法与 P16 冻结版逐字一致，仅导入路径随包结构调整。

## 安装

- Python ≥ 3.10
- `pip install -r requirements.txt`（Pillow：裁图与展平；NumPy：背景展平/夹具绘图）
- 仅 `pipeline.py`（从 PDF 生成 OCR）另需系统工具：Poppler 的 `pdftoppm`、
  Tesseract 及 `eng.traineddata`。位置可用参数或环境变量指定：
  `--tesseract / $TESSERACT_BIN`、`--tessdata-dir / $TESSDATA_DIR`、`--pdftoppm / $PDFTOPPM_BIN`。

## 书目录与配置（R4）

每本书一个目录，内含 `book.json`：

```json
{"pages": [101, 102], "blank_pages": [],
 "gold_dir": "gold", "seal": "gold_seal.json",
 "tiers": [200, 300, 360], "baseline_tier": 200, "crop_tier": 360,
 "control_seed": 7}
```

- `pages`：PDF 页码（可用 `--pages` 覆盖）。页码、路径、环境全部可配置，无任何写死值。
- `blank_pages`：经原图核实为空白/图版页的页码——这是空金标/空 OCR 被允许的
  **唯一**例外，每个门禁都会显式列出。
- 目录结构：`gold/pNNNN.txt`（人工真值）、`gold_seal.json`（真值 SHA-256 封存）、
  `work/ocr_<tier>/pNNNN.txt`、`work/tsv/pNNNN.tsv`、`work/scans_360/pNNNN.png`。

## 五个子命令

```bash
python3 -m ocrqa.review_tool lint  --book-dir BOOK     # 金标封存校验 + 归一化自检
python3 -m ocrqa.review_tool queue --book-dir BOOK     # 生成盲评队列（疑点+等量对照）
# 对每条队列项判定（CONFIRM_FIX 必须给出 --corrected，'' 表示明确删除）：
python3 -m ocrqa.review_tool decide --book-dir BOOK --item Q001 --decision KEEP
python3 -m ocrqa.review_tool decide --book-dir BOOK --item Q002 --decision CONFIRM_FIX --corrected "’"
python3 -m ocrqa.review_tool apply --book-dir BOOK     # 全部通过门禁后才写 corrected/
python3 -m ocrqa.review_tool score --book-dir BOOK     # 双轨评分 + 效率指标
python3 -m ocrqa.pipeline --pdf BOOK.pdf --pages 101,102 --work-dir BOOK/work
```

队列网页 `queue/queue.html` 可直接用浏览器打开逐条看裁图判定；裁图路径相对
网页自身，OCR 文本全部经 HTML 转义显示（R2）。

## 失败关闭门禁（R1 / R3）

- `lint`：封存哈希不一致 → 退出码 2（不再「打印警告却报成功」）。
- `queue` / `score`：任一非空白页的任一档 OCR 缺失或为零字节 → 退出码 3，
  逐页列明。源起：照片式灰底扫描曾让 Tesseract 在 7/10 页**静默返回空文本**
  （退出码 0、无警告）；`pipeline.py` 本身同样以退出码 3 拦截空输出。
- `decide`：`CONFIRM_FIX` 缺 `--corrected` → 退出码 4；同一条目重复判定 → 拒绝。
- `apply`：以下任一成立则**拒绝且不写任何文件**（退出码 5）：审核未完成、
  决定记录重复或含未知条目、`CONFIRM_FIX` 缺替换文本、基线 OCR 在建队列后被
  改动（哈希比对）、同页确认修订的跨距重叠冲突。
- `score`：评分前再验封存；修正串先归一化再算编辑距离（P16 勘误的回归防线，
  `lint` 内置自检）。

## 指标正名（统一口径，2026-10-23）

P16–P18 研究记录沿用了机器学习的 precision/recall 名称，容易误读。自 v0.2.0 起：

| 名称 | 定义 | P18 值 |
|---|---|---|
| 人工审核有效产出率 (human-review useful yield) | 经人工确认且落在真标点错误位点上的修订数 / 受审疑点数 | **46.9%**（23/49） |
| 机械疑点命中率 (mechanical flag hit rate) | 跨距与真位点重叠的疑点数 / 疑点数（不看人工判定） | **61.2%**（30/49） |
| 本书人工修订覆盖率 (this-book coverage by confirmed corrections) | 被确认修订覆盖的真位点数 / 真位点总数 | **37.1%**（23/62） |

与既往数字的关系：P16 的「Precision 53.5% / Recall 85.2%」、P17 的「28.0% / 87.5%」
按新口径即有效产出率与覆盖率；46.9% 不是检测器原始精度，61.2% 与 46.9% 是同一批
疑点的两种统计（一个看跨距重叠、一个看人工判定结果），不得混用。覆盖率是语料
错误结构的函数（本书错误以字母乱码为主轴时可低至 37.1%），不是工具常数。

**人工耗时测量局限**：决定日志的时间戳是按页批量落盘的，首末跨度（P18 为 283 秒）
只是真实人工耗时的**下限**；队列建成至判定完毕的墙钟（约 396 秒）含准备与交互
开销。两者都不是秒表实测，本项目不作任何「每条耗时」或「节省工时」的宣称。

**对照与盲法，如实说明**：对照项与疑点等量、随机抽自基线标点位、中性编号混编，
但三档读数就展示在条目上，审核者可以推断条目类别；疑点/对照映射是普通可读文件，
靠流程约定封存、非密码学密封。这是「编号隐藏的混合队列」，不是严格双盲试验。

## 合成测试包与测试

`fixtures/synthetic_book/` 是完全合成的微型书（自创英文短文 + PIL 绘制页图 +
脚本派生的三档 OCR），不依赖任何未公开扫描件：

```bash
python3 -m unittest discover -s tests -v   # 19 项：端到端 smoke + 全部失败关闭反向测试
```

## 许可

代码 MIT（见仓库根 LICENSE）。合成夹具文本为本仓库原创，一并 MIT。
