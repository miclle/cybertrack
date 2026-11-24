# 原理图与 PCB 制板条件

v2 使用一块 96 × 80 mm 的四层主板。带右前脸 Seeed 114993115 摄像头的版本为 **A2**。用嘉立创 EDA 专业版打开对应的 `.eprj3`，复制工程时保留同目录的原理图、PCB 和工程配置。两个修订的生产包、针序和固件需分别核对。

| 修订 | 设计及制造文件 | 装配及验证 |
|---|---|---|
| A2 摄像头主板 | [八页原理图与 PCB](../hardware/pcb/CyberTrack-A2/CyberTrack-A2.eprj3) · [Gerber、钢网及钻孔](../hardware/pcb/CyberTrack-A2-Gerber.zip) · [装配 STEP](../hardware/pcb/CyberTrack-A2-STEP.zip) | [原理图、布线与生产文件校验](../hardware/pcb/verification-A2.json) · [GPIO、供电与 J17 针序](../hardware/pcb/camera-revision/README.md) · [右前脸 FreeCAD 试装](../hardware/model/studies/front-camera/README.md) |
| A1 主板 | [六页原理图与 PCB](../hardware/pcb/CyberTrack-A1/CyberTrack-A1.eprj3) · [Gerber 及钻孔](../hardware/pcb/CyberTrack-A1-Gerber.zip) · [装配 STEP](../hardware/pcb/CyberTrack-A1-STEP.zip) | [BOM](../hardware/pcb/BOM-A1.md) · [网表、DRC 及校验记录](../hardware/pcb/verification-A1.json) · [接口与 SW2 恢复检查](../hardware/pcb/README.md) |

此前的五页 KiCad A3 原理图记录了面包板、L298N 和外接模块的接线，用于追溯旧样机。[历史原理图与 PDF](../hardware/schematic/README.md)

## 下单前核对

- **电气与装配版本。** 按所选修订核对电源极性、保险、连接器型号与针序、DNP、开关触点和额定电流。A2 还需核对原装 FPC 接触面和补强层厚度，按模组 1 脚对应 J17 第 24 脚逐针检查。按 A2 的 PDM 麦克风、扩展器和摄像头分配准备专用固件。[A2 针序与装配要求](../hardware/pcb/camera-revision/README.md)
- **板厂与贴片厂。** 用修订校验清单比对生产包 SHA-256，回读层序、板框、孔槽和阻焊。A2 的焊盘内过孔需要板厂确认树脂填孔、盖铜与整平工艺。J17 有 24 个信号焊脚和 4 个固定焊盘，贴片厂需确认钢网、锡量与连接器平面度。[A2 制板与装配](../hardware/pcb/camera-revision/README.md#a2-制板与装配)
- **机械与检修。** 按 X 向左、Y 向后、Z 向上的整机坐标核对板底焊点、螺钉、天线净空、散热片、线束和液路。A2 的 FreeCAD 记录覆盖拆顶盖后开锁、持尾及拔出排线的行程。首件用同批模组、连接器和实际工具复核操作空间、锁扣行程及接触可靠性。[插拔间隙与假设](../hardware/model/studies/front-camera/a2-service-check.json) · [整机装配](assembly.md)

## 首板检查与记录

1. 断电逐针核对电源、地、外接开关和连接器；记录板号、装配 BOM、保险、跳线及 DNP 状态。A2 先在断电状态验证 J17 的电源及地线映射，再接模组。
2. 使用限流电源分阶段检查输入保护、主控和执行器供电。用假负载验证上电、复位、SW2 断开与快速重合，记录各路输出和主控电压。重新合上 SW2 后，旧动作应保持停止。[电源测点](../hardware/architecture/README.md) · [主板验证项目](../hardware/pcb/README.md#样板验证)
3. A2 首件测量 1.8 V、2.8 V 的上掉电顺序、关断漏电和 PCLK 时序。使用 A2 固件在手机端测 VGA 预览帧率与帧间隔，同时运行音频、履带和超声波，记录电压跌落、闭壳温升及停止延迟。首轮目标为至少 15 fps，实际结果待测。[并发与首板判定](../hardware/pcb/camera-revision/README.md#并发与首板判定)
4. 用装机电池与实际低压负载分别测启动峰值、持续电流、压降和温升，再测允许的组合负载。测量记录关联板号、固件、仪表、工况、阈值和异常，作为量产放行依据。[整机验证计划](verification-plan.md)
