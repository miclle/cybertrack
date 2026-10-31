# 通过完整固件主机验证原话

此前完整固定集将前置状态附在用户原话前，并由静态夹具返回接受。实际控制守卫、参数拒绝和动作计时已有单独检查。本入口把这些环节连接起来，保留历史测试，另验证只发送用户原话的真实平台调用。

## 复用范围

主机程序从 prepared 源码提取实际 DoToolCall、Property／McpTool 序列化、十二个工具注册及回调、动作票据入口、Reply 序列化，并编译同版控制守卫。它复用默认参数、校验、票据去重、来源仲裁、拒绝结果、序列、计时与取消。

Application::Schedule 在主机立即执行。时间由输入发送后的实际调用时刻驱动，以最长 5 ms 的步长推进控制循环。没有 GPIO、串口、HTTP 设备或输出回调。测距固定为 600 mm，由真实 Reading 序列化器生成新鲜读数。

回执里的 device_id／boot_id 是固定桩值，source／actuator_backend 等常量沿用序列化源码；执行位置由外层 scope、主机二进制摘要及构建清单共同标识。主机检查不测实际调度延迟、驱动、供电、声音、机械输出或传感器。

## 三个明确场景

| 原固定集前置条件 | 主机初始化 |
|---|---|
| 在线、空闲、四路关闭、距离有效 | 输出关闭，模拟 600 mm 新鲜读数 |
| 70% 前进，原截止尚未到 | 前进 30 秒、70%，从输入发送时刻开始计时 |
| 可能有动作或序列运行，明确停止 | 前进 30 秒后吹泡泡一秒的活动序列 |

场景从原语料的 context 显式映射，未知条件拒绝运行，不静默退回空闲。前置动作使用保留的引导 RPC 编号，平台实际 RPC 编号原样送入分发器；重复编号能触发真实去重。

工具请求由实际分发器验证后才进入回调。MCP 结果原样转交平台，错误也保持原消息。轨迹保存调用、平台编号、完整结果、参数与操作回执。结束时按实际结束时刻重新计算最终状态，未发生调用的用例也有终态。

## 编译与独立协议检查

需要完整 checkout、已准备的同版固件源码和 ESP-IDF cJSON，不自动下载或刷写。

```sh
python3 scripts/build_firmware_host.py --source build/xiaozhi-ct61-src --output build/full-firmware-host
python3 scripts/check_firmware_host.py --executable build/full-firmware-host/firmware_host
```

构建器核对 prepared 的控制头文件与仓库来源，生成含二进制及输入摘要的 manifest.json。协议检查把固定集的 80 份预期调用作为合成测试输入，通过实际分发和回调核对守卫，再测非法参数、未知工具、重复编号和无效停止请求。停止场景另推进至第 60 秒，检查后续步骤没有恢复。它验证主机工具链，不构成 80 条模型成绩。

统一检查的 `--source` 路径会运行构建器与协议检查。开始平台采集前，应复制二进制到固定文件，避免其他构建替换正在使用的程序。

## 平台采集

```sh
cp build/full-firmware-host/firmware_host build/firmware-host-ct61-frozen
python3 scripts/capture_lingxi.py \
  --connection "$CONNECTION_FILE" --tools "$TOOL_SCHEMAS" \
  --role firmware/esp32-audio/role-prompt.txt --model deepseek-v4-flash \
  --corpus docs/validation/voice-cases.json \
  --firmware-host build/firmware-host-ct61-frozen --raw-text --audio-packets \
  --output "$NEW_CAPTURE"
```

连接文件仍须私有且不提交。此模式要求原话文本或合成语音，状态只在平台实际查询后返回；它自带真实参数校验，不再叠加独立参数门。每例用实际调用前缀重放，同一模型输入不会被额外填入预期答案。

平台评分继续使用原 80 条预期调用和顺序。缺查询、参数错误、额外调用、禁止动作和缺例都继续计分。历史带场景输入与本组原话输入分别保留，跨组差异需要结合输入、回执和采样共同解释。
