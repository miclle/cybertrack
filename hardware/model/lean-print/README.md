# 精简打印项目 · 24 件、6 盘

清水瓶与泡泡液瓶直接放入背包。第 3 盘删除两个瓶托和两片识别条，第 1 盘更新 PP04、第 6 盘更新 PP03。六盘件数依次为 **1、10、8、2、1、2**。第 1、3、4、6 盘需重切，第 2、5 盘的切片缓存逐字节保留。[下载 3MF](CyberTrack-Lean-6plates.3mf) · [现行回读](../bottle-backpack-direct-fit.json)

## 验证与复现

在 Bambu Studio 打开项目，按盘核对零件、支撑、首层路径与切片结果。两瓶直接放在湿舱底面，PP03 和 PP04 已更新。当前几何与排盘的增量复现需要上一版 v2 双瓶输入，详见[整机模型](../README.md)与[回读清单](../bottle-backpack-direct-fit.json)。

## 历史 27 件排盘耗材

按当时的 27 件排盘各打印一次，P2S、0.4 mm 喷嘴和 Bambu PLA Basic 的切片估算合计 **920.28 g、22 小时 8 分 46 秒**。[历史逐盘记录](../../../docs/validation/evidence/lean-print-estimate.json)

第 1、2、4、5 盘读取项目缓存，第 3、6 盘用同版 Bambu Studio 在临时目录重切。第 3 盘为 59.52 g，第 6 盘为 239.28 g。两盘均输出估算，日志均报告 `Invalid T command (T65535)`，第 3 盘另有 `ZFiller` 诊断。此处仅用于成本预算。打印前仍需在 Studio 中检查诊断、预览路径并切片保存。如需复核，请使用[当时的估算脚本](https://github.com/miclle/cybertrack/blob/06342c8bebe0eacdbd414c1e3b4887b975d80913/scripts/estimate_lean_print.py)与哈希匹配的 27 件排盘副本。
