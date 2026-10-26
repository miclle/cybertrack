# 0.51 六组合并打印候选

**PP02 已于 2026-10-26 局部更新**：Ø32 mm 偏心孔、孔心上移 1.3 mm、底部 7.5 × 2.3 mm 缺口、20 mm 宽支脚，删除近侧前长槽壁和前横挡块。其余打印件保持。最新尺寸与配合限制见[调整说明](../../../docs/print-consolidation.md)及[报告](../pp02-adjustment-audit.json)；缺口两侧与现有枪体模型仍相交，暂不作为配合通过的打印定版。

完整说明见[合并设计](../../../docs/print-consolidation.md)，回读与来源映射见[检查报告](../print-consolidation-audit.json)，[图册](print-parts.pdf)展示六件外形。

| 编号 | 打印件 | STL | STEP |
|---|---|---|---|
| PP01 | 水枪底托 | [STL](PP01-WaterCradle.stl) | [STEP](PP01-WaterCradle.step) |
| PP02 | 泡泡枪底座 | [STL](PP02-BubbleCradle.stl) | [STEP](PP02-BubbleCradle.step) |
| PP03 | 双瓶背包及桶座 | [STL](PP03-Backpack.stl) | [STEP](PP03-Backpack.step) |
| PP04 | 底盘及湿舱隔板 | [STL](PP04-LowerTub.stl) | [STEP](PP04-LowerTub.step) |
| PP05 | 冠盖及装甲饰件 | [STL](PP05-Crown.stl) | [STEP](PP05-Crown.step) |
| PP06 | 固定颈架 | [STL](PP06-Neck.stl) | [STEP](PP06-Neck.step) |

每件一个连通实体；STL单位按mm生成，XY居中、最低点Z=0，仍保留整机轴向。没有确定最佳打印朝向、支撑或材料参数。网格线性偏差0.08 mm、角度偏差0.15 rad；导出后检查封闭性、非流形边及与CAD壳数一致的边界分量。PP04含两处原有封闭内腔，具有三个闭合边界分量，但仍为一个连续打印实体。仅供切片和试配准备，不代表制造放行。

FCStd内的六个PP一级零件保存同一几何；主模型只保留履带动力分组。原融合输入及59个隐藏检查空间从主模型清除，保存在独立[设计源档](../source/CyberTrack-design.FCStd)供追溯，不要重复打印。本目录仅覆盖六组合并件，不是全机打印包。STEP可能存在曲面交换差异，以原生FCStd为几何依据。

本次独立STEP回读中，PP03背包体积差约34.687 mm³、PP05冠盖约4.358 mm³，超过0.01 mm³比较阈值，不能视为原生曲面等价。打印使用直接从原生实体生成并验证的STL；精确几何以整机FCStd内对应融合件为准。

0.53电源开关安装座属于六件合并范围之外的折面顶盖，已在整机中更新；本目录PP01–PP06的几何保持，见[安装说明](../../../docs/power-switch.md)。

0.55：PP06中央基座/鞍座随15芯净径10通道更新；PP06 STEP/STL和预览已同步，其他五件保持。见[通道专项](../../../docs/cable-passage.md)。这不关闭PP02既有配合冲突，也不构成制造放行。
