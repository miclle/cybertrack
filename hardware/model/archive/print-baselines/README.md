# 已清理的历史打印基线

2026-10-31 按“模型只保留当前版本”的要求移除 `CyberTrack-34parts-6plates.3mf`，同时移除 `print-ready/` 中旧四盘、五盘模型。当前 [Ready](../../print-ready/README.md) 与 [Lean](../../lean-print/README.md) 项目保留；历史检查 JSON 的路径、哈希和结论原样保留，不作为当前文件存在的声明。

原始六盘交付来自提交 `8552155`，当时的路径为 `hardware/model/print-ready/CyberTrack-Ready-6plates.3mf`，SHA-256 为 `aa53bac408cfa8f8289c48bfbee61ee6e9af5d6756091a1b8b1fc9027d263553`。其后曾在本目录作为 34 件打印基线保存。

旧四盘／五盘／34 件六盘及 Lean 29 件生成、对照脚本仅供历史复现，需在独立的匹配历史修订中恢复当时输入，不能对当前项目直接运行。当前 `scripts/check_backpack_release.py` 及 `scripts/check_print_release.py` 的当前版本检查分支均不读取已删除的旧模型。
