# 已清理的历史打印基线

2026-10-31 按“模型只保留当前版本”的要求移除 `CyberTrack-34parts-6plates.3mf`，同时移除 `print-ready/` 中旧四盘、五盘模型。当前 [Ready](../../print-ready/README.md) 与 [Lean](../../lean-print/README.md) 项目保留；历史检查 JSON 的路径、哈希和结论原样保留，不作为当前文件存在的声明。

原始六盘交付来自提交 `8552155`，当时的路径为 `hardware/model/print-ready/CyberTrack-Ready-6plates.3mf`，SHA-256 为 `aa53bac408cfa8f8289c48bfbee61ee6e9af5d6756091a1b8b1fc9027d263553`。其后曾在本目录作为 34 件打印基线保存。

当前两个六盘项目使用 `python3 scripts/check_print_release.py` 校验。复核旧排盘时，请按原修订恢复输入和[当时的检查脚本](https://github.com/miclle/cybertrack/blob/06342c8bebe0eacdbd414c1e3b4887b975d80913/scripts/check_print_release.py)。
