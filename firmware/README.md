# 固件

A4 与 A1 定制主板分别使用[对应的 ESP32-S3 应用构建](esp32-audio/README.md)，通过灵矽语音或局域网网页控制行走、喷水与泡泡。三路独立计时，BOOT 与全部停止取消剩余步骤。源码、最近部署和平台角色分别见[当前状态](../docs/current-status.md)与[版本清单](current.json)。

| 工程 | 用途 |
|---|---|
| [ESP32-S3 应用](esp32-audio/README.md) | 音频、OLED、联网、MCP 工具与本地执行器。[接口手册](CAPABILITIES.md) |
| [通用 C11 核心](src/) | 离线协议、受限动作和运行层，使用虚拟时间及假板卡测试。[实施计划](PLAN.md) · [协议契约](PROTOCOL.md) |
| [联网台架](esp32-linx/README.md) · [电机台架](esp32-motor-bench/README.md) | 分项测试有各自的接线、固件与供电记录，按原工况查阅。[台架记录](../docs/validation/bench.md) |

独立板无负载启动和 MOS 喷水台架的验证固件已归档。当时的源码、板卡条件与实测入口见[无负载检查](esp32/README.md)和[台架记录](../docs/validation/bench.md)。早期面包板软件报告可按版本号在[清理前的固件目录](https://github.com/miclle/cybertrack/tree/04ed36b87a49dd381d1a0d2fdd5cc9ac988489f4/firmware/esp32-audio)查阅。

## 本地编译与验证

要求 C11 编译器、CMake ≥3.16，运行测试另需 Python ≥3.9。JSON 解析器已随源码固定版本保存，构建无需联网或硬件。在仓库根目录执行：

```sh
cmake -S firmware -B build/firmware-host -DCMAKE_BUILD_TYPE=Debug
cmake --build build/firmware-host
ctest --test-dir build/firmware-host --output-on-failure
```

Clang／GCC 可在首次配置时加 `-DCMAKE_C_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer'`。构建输出位于已忽略的 `build/`；测试使用虚拟时间，不等待真实动作时长。测试记录见[主机验证](tests/README.md)。仅编译 C 库时使用 `-DBUILD_TESTING=OFF`，无需 Python。

## 通用控制核心已实现的边界

本节描述 `src/` 的通用核心。单活动槽位与本地使能契约不用于概括当前面包板的三路并行行为。

- `include/cybertrack/control.h` 与 `src/control.c`：`BOOT → DISARMED → READY → ACTIVE`，停止／故障进入锁定状态；上电无输出，本地使能后才能提交动作。
- 行走、水枪、泡泡共用一个活动槽位，不排队、不组合；本地期限到达时撤销逻辑输出。停止幂等；松开停止或故障消失都不会自行恢复动作。
- 会话断开／替换撤销使能；活动中断线锁定故障。校验动作类型、方向、速度档、时长、会话、序号、开始执行期限及计时溢出；时钟回退撤销输出。
- 限制值为零即能力不可用。测试数值仅为合成用例，不是台架建议值，也不构成可用的硬件配置。
- `include/cybertrack/protocol.h` 与 `src/protocol.c`：MCP 封装、初始化／发现／调用、严格 JSON 参数校验、有界原响应缓存、模拟传输会话与新鲜度门槛。停止优先于缓存及动作时效检查；远程接口不能使能。新解析与缓存重读内存失败会撤销逻辑输出、保留原缓存并要求本地重新使能，已通过逐次分配失败注入。
- `include/cybertrack/runtime.h` 与 `src/runtime.c`：启动先关断、单轮本地事件优先、周期时限与输出应用、条件喂狗、运行层错误锁定及响应抑制。板级回调契约与尚未验证项见[运行层](RUNTIME.md)；没有默认板型实现。

- `inputs.h`／`inputs.c`：逻辑输入去抖、停止／故障立即断言与已观察脉冲锁存；`inbox.h`／`inbox.c`：4 槽消息副本、原始元数据保持、断线优先及溢出关闭。详见[运行层契约](RUNTIME.md)。

- `link.h`／`link.c`：两层分片、连接与握手完成门槛、接收／发送超时、退避重连、发送失败关闭。通过假传输连接实际运行层，契约见[接收边界与连接流程](TRANSPORT.md)。

核心产生逻辑目标，独立协议层负责 JSON 解析，运行层通过板级回调应用目标；无负载检查工程已使用 ESP-IDF 时钟和 FreeRTOS 调度运行控制核心；该无负载工程仅 GPIO0 用作临时停止输入；通用核心的完整运行层、执行器 GPIO／PWM、网络鉴权尚未移植。左右轨道正值均表示车体向前，左转暂定左右反向原地转向；这是通用核心待板级验证的控制策略。通用核心速度档与实际 PWM、速度没有预设换算；面包板 ct21 的映射与四方向反馈见[台架记录](../docs/validation/bench.md)。

完整的存储、恢复和板级适配边界见[运行层](RUNTIME.md)、[恢复流程](RECOVERY.md)和[测试说明](tests/README.md)。
