# 精简打印项目 · 21 件、6 盘

六盘件数依次为 **1、8、7、2、1、2**。第 4 盘含 A1 托架，第 5 盘为含双喇叭内支座的 PP07，六盘均需切片。已移除旧独立板卡托架和上压框。[下载 3MF](CyberTrack-Lean-6plates.3mf) · [回读清单](../pcb-speaker-fit.json)

## 验证与复现

在 Bambu Studio 打开工程，逐盘检查支撑、首层与切片。双瓶直接放在湿舱底面，头舱使用定制主板。[整机模型与增量复现](../README.md)

## 历史 27 件排盘耗材

按当时的 27 件排盘各打印一次，P2S、0.4 mm 喷嘴和 Bambu PLA Basic 的切片估算合计 **920.28 g、22 小时 8 分 46 秒**。[历史逐盘记录](../../../docs/validation/evidence/lean-print-estimate.json)

第 1、2、4、5 盘读取项目缓存，第 3、6 盘用同版 Bambu Studio 在临时目录重切。第 3 盘为 59.52 g，第 6 盘为 239.28 g。两盘均输出估算，日志均报告 `Invalid T command (T65535)`，第 3 盘另有 `ZFiller` 诊断。此处仅用于成本预算。打印前仍需在 Studio 中检查诊断、预览路径并切片保存。如需复核，请使用[当时的估算脚本](https://github.com/miclle/cybertrack/blob/06342c8bebe0eacdbd414c1e3b4887b975d80913/scripts/estimate_lean_print.py)与哈希匹配的 27 件排盘副本。
