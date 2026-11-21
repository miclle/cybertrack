# 第 6 盘补齐记录（历史 34 件排盘）

v2 现行打印使用 [24 件 Lean](../lean-print/README.md) 或 [26 件 Ready](../print-ready/README.md)。本目录的两件前侧甲已更新为封闭出线孔的 STL、STEP 和 BRep。双瓶直接放入背包，瓶托和识别条已移除。[现行几何回读](../bottle-backpack-direct-fit.json)

2026-10-26 的补齐工作将 12 个零件追加到第 6 盘，原五盘 G-code 保持一致。当时的 Bambu Studio 切片估算为 **1 小时 30 分、59.87 g**。最终候选通过 56 个关键截面的路径检查。支撑清理、装配公差、承载和层间强度仍需实物验证。[历史基线](../archive/print-baselines/README.md)

| 复核内容 | 记录 |
|---|---|
| 当时补了哪些件、怎样摆放 | [零件清单](../print-ready/completion-inventory.json) · [12 件方向图](parts-overview.png) |
| CAD 与导出件是否一致，原有 22 件是否保留 | [几何审计](geometry-audit.json) · [既有件检查](native-preservation.json) |
| 第 6 盘的首层和关键截面 | [首层预览](plate-6-preview.png) · [路径检查](path-check.json) |
| 六盘合并结果 | [交付检查](../print-ready/six-plate-delivery-check.json) |

第 6 盘所用的几何导出、候选切片和合盘步骤见[当时的复现说明](https://github.com/miclle/cybertrack/blob/06342c8bebe0eacdbd414c1e3b4887b975d80913/hardware/model/completion-print/README.md)。复现需要同一修订的模型副本。
