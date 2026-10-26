# 用户排盘快照与精简前历史记录

## 当前保存的 Ready 项目

2026-10-26，用户重新排盘并保存后，[CyberTrack-Ready-6plates.3mf](CyberTrack-Ready-6plates.3mf)保留现场 34 件组合，只调整了中文盘名。盘序为：底盘；底盘与电控配件；双枪支架与顶盖；头壳；主控托盘与冠盖；背包、瓶托与 MOS 配件。模型、位置及工艺未因改名改变；保存的文件不含缓存 G-code，后续打印须重新切片。没有向打印机发送操作。

这份现场项目仍有已取消的 5 个压框及旧承板。新的 29 件减料方案见[Lean 精简项目](../lean-print/README.md)，两份项目的排盘不同，不能混用盘号或估算。当前 Ready 文件不能作为历史路径校验基线。

## 精简前的原始切片记录

原始 34 件、6 盘切片文件已独立归档为[固定校验基线](../archive/print-baselines/CyberTrack-34parts-6plates.3mf)，SHA-256 与原交付一致。下面的盘名、时间、哈希与保护关系均描述该历史版本，不描述用户最新排盘。

2026-10-26。原始交付为 **34 件、6 盘**，当时已在 Bambu Studio 中打开。遗漏的 5 个装配件和 9 个外观特征经两组合并，形成第 6 盘 12 件；上下两个线束护口已按用户要求取消。清单与装配方式见[补齐说明](../completion-print/README.md)，逐项闭环见[完整性清单](completion-inventory.json)。原五盘模型、工艺和 G-code 保持，不影响正在执行的打印。

| 盘 | 内容 | 预计时间 | 耗材 |
|---|---|---:|---:|
| 01 Chassis | PP04底盘 | 3小时59分 | 164.39 g |
| 02 Accessories 14 parts | 底盖、L298N托架／压框、电池托板、左右侧框、PP06颈架、左右肩梁、线束桥、4个控制板压框 | 4小时17分 | 150.81 g |
| 03 Head shell | PP07头壳与固定装饰 | 4小时9分 | 154.22 g |
| 04 Crown and tray | PP05冠盖＋面包板托盘 | 3小时24分 | 154.04 g |
| 05 Backpack lid and gun cradles | PP03背包、LC04顶盖、PP01水枪底托、PP02泡泡枪座 | 5小时24分 | 264.39 g |
| 06 Completion parts | 双瓶托、效果板承板、点火MOS托架及压框、前舱饰件、双瓶标识 | 1小时30分 | 59.87 g |

合计约 **22小时43分、947.72 g**，为切片估算。每盘逐层打印，盘间手动更换；正在打印／已经打印的零件不重打。原[四盘文件](CyberTrack-Ready-4plates.3mf)作为历史交付保留；已打印的 VF01 验证框架和可选导孔试件未重复加入。

PP02 下缘避让与 LC04 安装柱连接已修复，四件的独立导出、朝向和支撑见[新增四件说明](../remaining-print/README.md)。第 5 盘 0.28 mm、3 墙、10% cubic；PP01 保留 0.5 mm 经典墙线，其余三件 0.6 mm Arachne，普通贴合支撑。33 个截面路径通过基线覆盖检查，路径碰撞检查执行且无切片警告；已查看[第 5 盘首层](../remaining-print/plate-5-preview.png)。

[五盘交付检查](five-plate-delivery-check.json)验证原四盘 G-code 字节不变，并核对 GUI 保存回读的 26 个网格体（22 个打印件＋4 个修改体），最大坐标回读差小于 0.000004 mm。为保留用户现场，先保存当前四盘快照；Studio 的 Save As 省略缓存路径，因此在核对几何、摆放和工艺后恢复原 G-code，保留当前设备／耗材设置，记录见[现场检查](current-snapshot-check.json)。

统一P2S／0.4 mm标准喷嘴、纹理PEI和用户确认的Bambu PLA Basic，体积流量上限21 mm³/s。底盘／配套盘原来使用Generic PLA的12 mm³/s限制；统一材料后重新切片，时间相应降低。保持各零件的实际层高、墙数、顶底层、填充和支撑参数，以对象设置覆盖全局参数：底盘／配套件0.24 mm、3墙；头部0.28 mm；冠盖四螺丝座局部100%填充／4墙；托盘3墙。

[交付检查](delivery-check.json)验证18个普通打印网格的顶点／三角形与来源逐项相同，4个螺丝座修改体保留，各对象工艺设置与来源一致、无网格修复。四盘均切片成功，无悬空警告，执行碰撞检查，首层含支撑及brim均位于256×256 mm平台内；[四盘首层路径图](four-plates-first-layers.png)已查看。实际结果见[result.json](result.json)，来源与对象映射见[manifest.json](manifest.json)。

合并后重新抽查[底盘12处](chassis-path-check.json)、[头壳20处](head-path-check.json)、[冠盖12处／托盘8处](companions-path-check.json)关键路径，均通过既定覆盖筛查。覆盖是挤出路径证据，不是全层连通、实际强度或装配验收。已有14件共盘的精确嵌套间隙检查继续适用，因为模型与排布保持。首次实物仍需清理支撑并试装。

完整[切片日志](run.log)保留官方结束模板的T65535诊断和一条ZFiller诊断；最终return_code=0、四盘warning均为空。没有把CLI成功写成实机验收。

复现：`python3 scripts/compose_ready_prints.py`生成并切片；在安装Pillow的Python环境运行`python3 scripts/check_ready_prints.py`检查网格、设置、边界并生成预览。FreeCAD关键截面报告与此前独立件报告共同保留；此前仅合并四盘时未改主模型。后续新增第 5 盘只修改 PP02 与 LC04，见新增四件的几何审计。追加脚本见 `preserve_current_prints.py`、`append_remaining_plate.py` 和 `finalize_remaining_project.py`；不要重跑旧四盘生成器覆盖用户当前设置。

第 6 盘交付：[56 处路径检查](../completion-print/path-check.json)与[六盘检查](six-plate-delivery-check.json)。原五盘文件及四盘文件作为历史版本保留；此前[五盘遗漏报告](completeness-audit.md)已由本次闭环清单解决。

## 清理后的验证入口

运行 `python3 scripts/check_print_release.py`，验证当前主模型、Lean 的 29 件清单、六盘缓存路径与固定历史基线的保护关系，见[报告](release-check.json)。清理删除了重复切片工程/G-code、GUI快照、临时备份和已取消护口试验；比较结果、工艺配置、单件STL/STEP与关键验证记录保留。四盘/五盘基线仅用于核对历史盘未变，打印使用六盘文件。历史实验脚本可能需要先重新生成中间输入，不再依赖清理前的缓存立即复跑。详见[清理清单](cleanup-report.json)。
