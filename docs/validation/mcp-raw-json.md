# ct70：拒绝被截断成合法前缀的机器人请求

本轮独立提取[未采纳数组研究](native-step-inputs.md)发现的原始 JSON 准入缺陷，不推广数组接口。十二项公开工具、`steps_json` 字符串契约、5991 字符角色及网页接口不变。ct70 是源码候选，最近记录部署仍为 ct45；没有修改平台配置或刷写设备。

## 问题与修复

cJSON 的字符串以零字符结束。`"direction":"forward\u0000extra"` 会变成 `forward`，`"edit":"cancel\u0000extra"` 会变成 `cancel`；仅在解析后检查枚举无法发现被丢弃的后缀。固定旧 ct68 主机中，前者被接受并启动逻辑输出，后者可以取消已有草稿。

ct70 在 WebSocket、MQTT 和 SDK 直接字符串入口，保留原始消息长度，先检查机器人 `tools/call` 的零字符及实际 Unicode 零转义，再进入参数准入。命中时返回错误并锁定本轮失败，不自动停止已有合法动作，也不允许同轮换工具补做；合法全停仍保留，新识别输入可恢复。

检查按反斜线转义层级区分 `\u0000` 与字面量 `\\u0000`，不将普通文字误判为零字符；普通非机器人帧不受此门禁影响。请求编号转换与原 SDK 的数字编号路径保持一致，小数或越界数字不能借原始检查的整数筛选绕过拒绝。它不是一次全协议 JSON-RPC 合规重构。

这是明确的编码／解析边界防护，不理解用户意图，不能解决自然语言误停、含糊指令或过程播报。既有内层序列字符串校验保留。

## 验证证据

- [16 组实际调度回放](evidence/ct70-raw-mcp/native.json)全部通过，[ASan／UBSan 同矩阵](evidence/ct70-raw-mcp/native-asan.json)也全部通过。覆盖方向、组合、工具名、键名、取消和改稿的零字符；已有行走不被畸形停止中断、合法停止仍执行；同轮禁止补做、新输入恢复、排队回调隔离，以及合法旧字符串序列。
- [旧 ct68 对照](evidence/ct70-raw-mcp/baseline.json)在同一矩阵有 11 项不满足新约束，属于同一缺陷的不同后果，不计成 11 个独立漏洞。
- C++ 消毒器测试直接编译 prepared SDK 的原始字符串入口，确认畸形内容不转交解析后入口；编号边界和实际零字节尾随内容也拒绝。共享检查覆盖裸消息与外层 MCP 信封、1–8 个反斜线层级、合法停止、非机器人与普通文本。WebSocket／MQTT 的完整网络回调随 ESP-IDF 构建编译，但没有声称运行过真实网络注入。
- [既有 88 条平台请求兼容回放](evidence/ct70-raw-mcp/historical-compatibility.json)的每次完整回执和同观察时刻终态与 ct68 原记录一致。保留原 77/80、5/8 模型成绩，**没有新采模型或把它们改计通过**。
- [公开契约检查](evidence/ct70-raw-mcp/contract-check.json)确认实际编译工具目录与 ct68 的十二项定义逐项相同，角色摘要与 ct45 最近记录同步相同。
- [16 组统一软件检查](evidence/ct70-raw-mcp/software-checks.json)通过，含 98 项 Python 测试、原 MCP／HTTP／音频、80／8 语义夹具、停止、失败隔离、相对改稿及含糊动作回放。

[完整固件记录](../../firmware/esp32-audio/verification-ct70.json)：ESP-IDF 5.5.1 编译通过，应用 2,715,792 字节。源码 ct70 与最近记录部署 ct45 的两份本地镜像分别核对字节数及 SHA-256，见[版本检查](evidence/ct70-raw-mcp/version-check.json)。镜像核对不是设备刷写或运行证明。

## 复现

完整 checkout 中准备 ct70 源码与工具链后运行；所有检查不连接设备：

```sh
python3 scripts/build_firmware_host.py --source build/xiaozhi-ct70-src --output build/ct70-raw-host
python3 scripts/check_mcp_raw.py --executable build/ct70-raw-host/firmware_host --output output/ct70-raw-mcp/native.json
python3 scripts/build_firmware_host.py --source build/xiaozhi-ct70-src --output build/ct70-raw-asan-host --sanitize
python3 scripts/check_mcp_raw.py --executable build/ct70-raw-asan-host/firmware_host --output output/ct70-raw-mcp/native-asan.json
python3 scripts/verify_improvements.py --source build/xiaozhi-ct70-src
```

主机通过只用于测试传输的 `raw_params` 保留原始转义，调用返回即释放输入树，实际延迟回调使用 SDK 自己复制的值；工具目录与二进制摘要一起写入主机清单。它不会重写捕获的模型参数，也不宣称保留了平台原始 JSON 的重复键或每一字节布局。

旧应用部署、现场停止、真实扬声器、原语义与编排门槛均保持独立待验。下一步继续收敛自然语言误停和过程播报；部署候选时需另做设备时序与恢复验证。
