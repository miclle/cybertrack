# 机械装配与维护

先核对手里的打印件属于哪套排盘。Lean 和 Ready 均为 27 件、6 盘，盘号和切片缓存各自独立。Lean 第 3、6 盘需重切，Ready 六盘均需切片。装配时以保存的 FreeCAD 整机为几何依据，坐标 X 向左、Y 向后、Z 向上，前方为 −Y。[整机模型](../hardware/model/README.md) · [Lean](../hardware/model/lean-print/README.md) · [Ready](../hardware/model/print-ready/README.md)

## 底盘与动力

37R-520 电机经联轴器驱动两侧履带。维护一侧电机前，先释放联轴器、移开电源内托架及本侧履带，再按模型路径下取。VF01 已有双侧静态试配反馈，实际螺钉牙深、带线操作空间、底盖承载和反复拆装仍需核对。[VF01 试配](../hardware/model/drive-fit-fixture/README.md) · [动力接口](../hardware/components/drive-interface/README.md)

L298N 的现行支架由底盖承载，拆卸前要给端子和线尾留出空间。辰克 5 V 电池包低位平放，外形 116 × 70.5 × 19.5 mm。核对插头、线材弯曲和板上最高点后再盖合。[驱动板安装](../hardware/model/l298n-compact/README.md) · [电源与接口](../hardware/architecture/README.md)

## 电源开关与停止按钮

电源开关从底盘折面顶盖上方放入。挂耳孔距实测 14.8 mm，安装座按两颗 Ø2 × 6 mm 塑料自攻螺丝设计，固定前需试配导孔与挂耳。独立执行器断电 SW2 的额定值和实际切断效果仍待验证。[开关实物尺寸](../hardware/components/power-switch/README.md) · [安装检查](../hardware/model/power-switch-audit.json)

外接 BOOT 按钮预留在右肩内侧，候选为常开、自复位干接点，连接 GPIO0 与 GND。按钮型号、孔位公差、实物可达性以及复位时的引脚状态待核对。按下 BOOT 触发固件全停，松开后需要新指令。[按钮安装与空间检查](../hardware/model/boot-button-audit.json) · [接线表](wiring.md)

## 头舱与穿线

面包板、音频与屏幕作为一组装在独立浅托盘内。100 × 85 mm 是面包板平面尺寸，36 mm 是规划高度。拆冠盖后先断开 USB、收置超声波和跨舱线束，再取托盘。冠盖和托盘各用四颗螺丝，Ø2.1 mm 导孔需结合实际打印材料试拧。[头壳、配套冠盖及试拧件](head-shell-print.md)

颈部按 15 根导线、净径 10 mm 规划，已计入 BOOT 两线。主束经过中央限位桥，在托盘下方转向头舱左侧。独立上下护口已取消，穿线前需修整孔缘，核对实物束径、连接器、转弯和抽盘余量。[通道检查](../hardware/model/cable-passage-audit.json) · [颈部路线图](../hardware/model/cable-passage-layout.png)

超声波前脸并入 PP07，探头孔 Ø16.6 mm，中心距 26 mm。拆冠盖和托盘、收置线束并释放模块后，CAD 中的候选路径为后退 11 mm、上提 70 mm。仍需核对实际 PCB、针座、固定方式及装壳后的测距表现。[固定与空间记录](../hardware/model/ultrasonic-integration-audit.json) · [测距与前进保护](ultrasonic-ranging.md)

## 双枪与背包

从正面看，泡泡枪在左、水枪在右。两枪的降压模块各在枪体内，MOS 板按现行 Lean 方案胶固。PP02 泡泡枪底座采用复合孔口，装枪时需检查实物轮廓、软管、胶合保持与拆卸空间。测试供液时另记吸程、低液位、滴液、倒流与湿区隔离。[枪座修正](../hardware/model/remaining-print/README.md) · [低压效果控制](effects-control.md)

PP03 背包保留清水瓶，旧泡泡液瓶及其底托已移除，泡泡供液容器尚待确定。两侧桶座与上导环内径 35 mm。模块固定、防脱和导线保护需要实物数据，A2 的点火支路保持禁用装配。[背包几何与打印文件](backpack-35mm.md) · [原理图与装配状态](../hardware/schematic/README.md)

## 打印件与装配图册

PP01–PP07 是合并后的打印件编号。PP07 将头部下壳、前脸和固定装饰合为一件，须配套使用新版 PP05。只补打某个零件时，先核对它与相邻零件的修订。[单件文件](../hardware/model/print-parts/README.md) · [头部打印工艺](head-shell-print.md)

[69 页装配图册](../hardware/model/CyberTrack-assembly-and-service.pdf)记录 0.56 版的六向视图、部件位置和拆装图卡。查看位置可用图册，制作底盖驱动支架、头壳、枪座及背包时应以相应的现行模型为准。[制作与样机照片](../artifact/README.md)可用于比对实际装配。
