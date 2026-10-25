# 0.51 六组合并打印候选

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
