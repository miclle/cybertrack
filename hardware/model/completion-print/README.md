# 遗漏件补齐与第 6 盘

2026-10-27：泡泡液瓶底托与识别条已从 CAD、六盘项目及本目录独立导出中撤销。下文补齐数量和报告属于历史版本，现行清单见[背包修订](../../../docs/backpack-35mm.md)。

本目录为精简前的历史补齐记录。2026-10-26 用户取消 MOS 压框、将两块降压板移入枪体后，现行两件支架几何、27 件清单和打印顺序已转到[精简交付](../lean-print/README.md)；旧压框导出此前已清理；本目录旧 EffectTray／IgnitionMOSCarrier 的 STL、STEP、BREP 于 2026-10-31 移除，只保留 Lean 目录中的当前版本。

2026-10-26。已补齐先前遗漏的 5 个装配件、9 个外观特征。左右侧甲与对应嵌条各合为一件，因此新增 **12 个打印件，共用第 6 盘**。用户明确取消上下两个线束护口，主模型、设计源档和打印清单均已移除；现有孔位、限位桥及原五盘保持。

历史固定基线 `CyberTrack-34parts-6plates.3mf` 当时为 **34 件、6 盘**；旧模型已于 2026-10-31 清理，见[历史基线说明](../archive/print-baselines/README.md)。本盘预计 **1 小时 30 分、59.87 g**；首层及全部打印路径落在平台内，56 个关键截面覆盖检查通过，切片警告为空。已在 Bambu Studio 打开并经 GUI Save As 回读核对，38 个网格体（34 件＋4 修改体）坐标误差小于 0.000004 mm。前五盘 G-code 字节不变。

| 打印件 | 数量 | 方向与装配 |
|---|---:|---|
| WaterPod、BubblePod | 2 | 底面贴盘，保留原底部双孔及绑带导槽；先固定空瓶托，再放软垫、瓶和绑带 |
| EffectTray | 1 | 平底贴盘；与第 2 盘四个效果板压框配套 |
| IgnitionMOSCarrier、IgnitionMOSRetainer | 2 | 平底贴盘；托架及压框孔位保持，板边垫与紧固件另备 |
| ChestAudioPanel | 1 | 背面贴盘；薄胶贴在底盘前面 |
| PrintChestGuardL/R | 2 | 侧甲＋小嵌条一体，背面贴盘；原穿线孔保持，薄胶固定 |
| LowerChin、ChestBadge | 2 | 背面贴盘；对应前舱下缘和上沿位置薄胶固定 |
| WaterLidMark、BubbleLidMark | 2 | 背面贴盘，厚 0.8 mm；贴在对应背包标识位置 |

模型调整：效果板承板 9 处、点火 MOS 托架 2 处柱/壁相切导致非流形网格，已用半径 0.35 mm 局部连接补实；安装孔、PCB 接触面和原五盘对接件保持。前舱饰件背面退让 0.15 mm，为薄胶留空间；标识条厚度增至 0.8 mm，背面也留 0.15 mm。保持装配外形及孔位的检查见 [CAD 与独立导出](geometry-audit.json)、[既有 22 件保护检查](native-preservation.json)。STL 均为闭合单连通网格，无非流形边；独立 STEP 回读几何差小于 0.01 mm³。主模型 FCStd 是几何依据。

工艺：P2S／0.4 mm、PLA Basic、纹理 PEI；0.28 mm 层高、0.2 mm 首层、3 墙、0.6 mm 墙线、Arachne、10% cubic、顶底各 4 层、3 mm 外裙边；普通贴合支撑，顶间隙 0.2 mm、基础间距 4 mm。外观件平放减少支撑，瓶托直立保持导槽结构。0.24 mm 层高保守方案约 100.1 分／59.16 g，0.28／0.5 墙线约 91.9 分／59.24 g；最终 0.28／0.6 墙线合并复切约 90.0 分／59.87 g，时间减少约 10%。保留 3 墙及薄壁路径，不以空壳或删除导槽提速。路径报告中的保守方案右侧甲内部覆盖 53.9%受填充布局影响；最终候选全部 56 截面达到既定覆盖阈值。

前舱饰件采用薄胶粘接，0.15 mm 是设计胶层预算，须清理背面、先干装再固定；本轮没有验证胶材与实际保持力。瓶托、承板、板框按原螺钉/嵌件装配，软垫、绑带、魔术贴和紧固件不作为 PLA 零件。取消护口后保留原孔口，穿线前清理打印毛刺并用现有限位桥固定线束。

[12 件方向图](parts-overview.png) · [第 6 盘首层](plate-6-preview.png) · [路径检查](path-check.json) · [六盘交付检查](../print-ready/six-plate-delivery-check.json) · [遗漏项闭环清单](../print-ready/completion-inventory.json)。支撑清理、公差、装配、承载与层间强度仍需实物验证。仅安排被动安装件制造，不代表点火通电验收。

复现脚本：`prepare_completion_geometry.py`、`remove_print_grommets.py`、`slice_completion_prints.py`、`append_completion_plate.py`、`finalize_completion_project.py`。仅对匹配该历史修订的模型副本复现，不能直接用于现行 Lean 模型或覆盖已打印件。用户取消护口前的研究工程及原始切片已清理，结果只保留为历史数据；当前交付不含护口。
