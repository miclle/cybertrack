# 历史 CAD 检查报告

2026-10-25 归档。这里保存 23 份历次设计检查与回读快照，用于追溯设计变化；当前模型和当前生成流程的检查入口见[整机说明](../README.md)。

## 证据与路径

- 报告从 `hardware/model/` 移至 `archive/reports/`，文件内容逐字节保持，不重写日期、结论、源文件路径或哈希。归档前版本为 Git 提交 `a3b5fcade6e00541bd1bb9fcf5e413b2e45226c5`。
- JSON 中的路径、版本、文件哈希和检查结果描述生成时的状态；其中相对路径沿用原目录语境，历史绝对路径也不作为当前可运行入口。需要复现时，从对应 Git 历史恢复匹配的模型、脚本与输入。
- 部分报告的结构结论仍用于说明现行设计的来由，但不代表当前整机再次通过检查，更不代表制造、装配或实物验收。
- 当前生成器会更新的专项报告，以及图纸生成仍读取的范围报告，继续保留在上级目录。版本号较早不等于报告已失去当前依赖。

## 报告索引

| 历史检查范围 | 原始报告 |
|---|---|
| 0.35 双瓶旧护舱专项 | [bottle-backpack-0.35-audit.json](reports/bottle-backpack-0.35-audit.json) |
| 0.34 → 0.35 双瓶范围变化 | [bottle-backpack-0.35-change-audit.json](reports/bottle-backpack-0.35-change-audit.json) |
| 0.35 整机回读快照 | [bottle-backpack-0.35-readback.json](reports/bottle-backpack-0.35-readback.json) |
| 0.17 → 0.18 泡泡枪与整体圆环变化 | [bubble-gun-change-audit.json](reports/bubble-gun-change-audit.json) |
| 0.29 动力固定专项 | [drive-mount-0.29-audit.json](reports/drive-mount-0.29-audit.json) |
| 0.30 可拆端板动力专项 | [drive-mount-0.30-audit.json](reports/drive-mount-0.30-audit.json) |
| 0.31 动力维护专项 | [drive-mount-0.31-audit.json](reports/drive-mount-0.31-audit.json) |
| 0.29 动力固定范围变化 | [drive-mount-change-audit.json](reports/drive-mount-change-audit.json) |
| 0.29 → 0.30 动力维护变化 | [drive-service-0.30-change-audit.json](reports/drive-service-0.30-change-audit.json) |
| 0.30 → 0.31 动力维护变化 | [drive-service-0.31-change-audit.json](reports/drive-service-0.31-change-audit.json) |
| 0.37 → 0.38 双枪上仰 10° | [gun-pitch-0.38-audit.json](reports/gun-pitch-0.38-audit.json) |
| 0.37 头舱加高原始快照 | [head-lift-0.37-audit.json](reports/head-lift-0.37-audit.json) |
| 0.26 → 0.27 后护甲变化 | [rear-armor-change-audit.json](reports/rear-armor-change-audit.json) |
| 0.18 → 0.19 滴液唇移除 | [rear-drip-removal-audit.json](reports/rear-drip-removal-audit.json) |
| 0.19 → 0.20 旧后部管孔 | [rear-hose-port-audit.json](reports/rear-hose-port-audit.json) |
| 0.20 → 0.21 后部对称布局 | [rear-symmetry-audit.json](reports/rear-symmetry-audit.json) |
| 面包板整组布局前的独立扬声器适配 | [speaker-fit-audit.json](reports/speaker-fit-audit.json) |
| 0.27 → 0.28 顶部吸管布局变化 | [top-feed-change-audit.json](reports/top-feed-change-audit.json) |
| 0.26 实测探头布局变化 | [ultrasonic-change-audit.json](reports/ultrasonic-change-audit.json) |
| 0.22 → 0.23 水枪胶粘底托变化 | [water-gun-adhesive-audit.json](reports/water-gun-adhesive-audit.json) |
| 0.21 → 0.22 水枪夹持尺寸变化 | [water-gun-fit-audit.json](reports/water-gun-fit-audit.json) |
| 0.24 → 0.25 水枪双托管槽与尾线变化 | [water-gun-routing-audit.json](reports/water-gun-routing-audit.json) |
| 0.23 → 0.24 水枪侧挡与托管变化 | [water-gun-sidewalls-audit.json](reports/water-gun-sidewalls-audit.json) |

## 已移除的历史对比图

已移除 0.35→0.36、0.36→0.37、0.37→0.38、0.38→0.39 四组对比图及各自的渲染记录，共 12 个文件，并移除专用脚本 `scripts/render_backpack_comparison.py`。它们只用于展示阶段外观差异，不参与当前 CAD 或装配图纸生成；删除前内容可从上述 Git 提交恢复。文档保留对应版本的设计说明与检查报告入口。
