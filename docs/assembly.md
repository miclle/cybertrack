# 机械装配与维护

A2 的右前脸安装沿用 PP07 固定座。装好小散热片与后压片，开冠盖，从上方竖直插入原装 FPC，露铜面朝前，转动 J17 锁扣。维修时先开锁，夹住补强端上提。[A2 插拔模型、工序与净距](../hardware/model/studies/front-camera/README.md#a2-主板插拔检查)


Lean 21 件、Ready 20 件，各六盘。使用 Ready 时另打 A1 主板托架。整机坐标 +X 向左、+Y 向后、+Z 向上，前方为 −Y。[整机模型](../hardware/model/README.md) · [Lean](../hardware/model/lean-print/README.md) · [Ready](../hardware/model/print-ready/README.md)

## 底盘与动力

37R-520 电机经联轴器驱动两侧履带。维护一侧电机前，先释放联轴器、移开电源内托架及本侧履带，再按模型路径下取。VF01 已有双侧静态试配反馈，实际螺钉牙深、带线操作空间、底盖承载和反复拆装仍需核对。[VF01 试配](../hardware/model/drive-fit-fixture/README.md) · [动力接口](../hardware/components/drive-interface/README.md)

v2 使用 A1 板载 L298P；旧样机的独立 L298N 与底盖支架见历史装配记录。辰克 5 V 电池包低位平放，外形 116 × 70.5 × 19.5 mm。核对插头、线材弯曲和板上最高点后再盖合。[驱动板安装](../hardware/model/l298n-compact/README.md) · [电源与接口](../hardware/architecture/README.md)

## 电源开关与停止按钮

电源开关从底盘折面顶盖上方放入。挂耳孔距实测 14.8 mm，安装座按两颗 Ø2 × 6 mm 塑料自攻螺丝设计，固定前需试配导孔与挂耳。独立执行器断电 SW2 的额定值和实际切断效果仍待验证。[开关实物尺寸](../hardware/components/power-switch/README.md) · [安装检查](../hardware/model/power-switch-audit.json)

外接 BOOT 按钮预留在右肩内侧，候选为常开、自复位干接点，连接 GPIO0 与 GND。按钮型号、孔位公差、实物可达性以及复位时的引脚状态待核对。按下 BOOT 触发固件全停，松开后需要新指令。[按钮安装与空间检查](../hardware/model/boot-button-audit.json) · [接线表](wiring.md)

## 头舱与穿线

整机采用 A1 主板，板底 Z178 mm。四个 Ø2.8 mm 安装孔落在框架的四根支柱上，候选固定件为 Ø2.5 × 5 mm 螺钉。框架通过四个侧耳锁到 PP07，冠盖单独拆装。板底焊点、插头高度、螺纹保持力和麦克风声道需用首板核对。[主板与托架](../hardware/model/README.md#v2-头舱电子装配)

**左右各装一只同型号常规喇叭。** 断电、开盖，先装扬声器，再装 A1 托架。振膜朝外，原厂耳片对准 PP07 内侧的两个盲孔柱，在硬质前框与支承唇之间放闭孔泡棉（设计压缩厚度 1 mm）。每只用两颗 ST2.9 × 8 mm 候选螺钉配垫圈压住耳片。先用打印件试拧，确认两侧密封均匀、振膜和出声通路留空。[喇叭图纸](https://puiaudio.com/file/specs-ASE02808MR-LW150-R.pdf) · [头舱模型](../hardware/model/README.md#v2-头舱电子装配)

两只 8 Ω 喇叭用 Y 形线束同相并联到 J5。J5-1（SPK_P）分到两个正端，J5-2（SPK_N）分到两个负端，额定负载合计 4 Ω。两条引线分别固定在头舱内侧，留出拔插余量，避开麦克风声孔、摄像头排线和螺丝柱。检修时先拔 J5、移开托架，再拆目标喇叭。

首件从低音量开始，先逐只检查极性与出声，再同音量合播。在正前方 30 cm、50 cm 检查人声是否居中、左右响度是否接近；闭盖复测履带噪声、自播回声、失真、5 V 压降及功放温升后再确定音量上限。[CAD 回读](../hardware/model/pcb-speaker-fit.json)

旧版颈部按 15 根导线、净径 10 mm 规划，已计入 BOOT 两线。主束经过中央限位桥，在托盘下方转向头舱左侧。独立上下护口已取消，穿线前需修整孔缘，核对实物束径、连接器、转弯和抽盘余量。[通道检查](../hardware/model/cable-passage-audit.json) · [颈部路线图](../hardware/model/cable-passage-layout.png)

超声波前脸并入 PP07，探头孔 Ø16.6 mm，中心距 26 mm。拆冠盖和托盘、收置线束并释放模块后，CAD 中的候选路径为后退 11 mm、上提 70 mm。仍需核对实际 PCB、针座、固定方式及装壳后的测距表现。[固定与空间记录](../hardware/model/ultrasonic-integration-audit.json) · [测距与前进保护](ultrasonic-ranging.md)

## 双枪与背包

从正面看，泡泡枪在左、水枪在右。两枪的降压模块各在枪体内，MOS 板按现行 Lean 方案胶固。PP02 泡泡枪底座采用复合孔口，装枪时需检查实物轮廓、软管、胶合保持与拆卸空间。测试供液时另记吸程、低液位、滴液、倒流与湿区隔离。[枪座修正](../hardware/model/remaining-print/README.md) · [低压效果控制](effects-control.md)

清水和泡泡液各用一只 150 mL 候选瓶，直接放进 PP03 背包，瓶底落在 PP04 湿舱底面。PP03 封平原绑带缺口，PP04 填平原底托嵌件孔。两根软管从瓶顶接向各自的前枪，瓶口端各向下延长 6 mm。水管外径 5 mm 来自实测，泡泡管外径 4 mm 是 CAD 候选。[双瓶与软管回读](../hardware/model/bottle-backpack-direct-fit.json)

### 两只瓶怎么取

断电并处理残液后，抽出目标瓶的吸管并收在提瓶路径外，竖直取瓶，在机外补液。名义含盖包络均为 Ø48.8 × 114 mm，瓶顶高出背包上沿 24 mm。CAD 已验证每只瓶沿 +Z 上提 150 mm，期间另一只瓶与软管保持在位。[双瓶拆装检查](../hardware/model/bottle-backpack-direct-fit.json)

现场计时从瓶体已放入、吸管已接好开始，到瓶体完整离开背包为止。分别记录收管与提瓶时的卡滞、滴液或抓握困难；取瓶和装回分开计时。满／空液行走、转弯和急停时的瓶体窜动、跳出与溅漏，以及瓶盖密封与通气，均待实物验证。[维护记录方法](validation/README.md)

## 打印件与装配图册

PP01–PP07 是合并后的打印件编号。PP07 将头部下壳、前脸和固定装饰合为一件，须配套使用新版 PP05。只补打某个零件时，先核对它与相邻零件的修订。[单件文件](../hardware/model/print-parts/README.md) · [头部打印工艺](head-shell-print.md)

[69 页装配图册](../hardware/model/CyberTrack-assembly-and-service.pdf)记录 0.56 版的六向视图、部件位置和拆装图卡。查看位置可用图册，制作底盖驱动支架、头壳、枪座及背包时应以相应的现行模型为准。[制作与样机照片](../artifact/README.md)可用于比对实际装配。
