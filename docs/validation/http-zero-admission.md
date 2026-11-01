# ct75：网页控制拒绝零字符截断

## 缺口与修正

ct74 的 HTTP 请求体已经拒绝原始零字节，但没有拒绝 JSON 字符串中的 `\u0000`。cJSON 将字符串保存为零结尾的 C 字符串，后续 `strcmp` 或键名查找会忽略零字符之后的内容，可能将非法操作名、方向或草稿编辑解释为合法前缀。Host／Origin、令牌、请求窗口和动作限幅仍有效；本问题不意味着绕过这些条件。

本轮使用真实 `web_server.cc` 和 ESP-IDF cJSON 的原生 HTTP 测试复现：`set_speed\u0000extra` 没有在 HTTP 入口被拒绝，首个拒绝断言失败；该次运行随后中止，没有声称其他反例也在旧版逐一执行。[旧版证据](evidence/ct75-http-zero/baseline.json)

ct75 在解析 HTTP 请求体之前复用现有 `McpJsonContainsZero`，同时检查原始零字节与实际 Unicode 零转义。偶数个反斜线形成字面量文本，不被当成零字符；其他合法 Unicode 转义仍可解析。命中返回 HTTP 400／`invalid_request`，不会进入控制回调，不撤销会话，随后合法状态与停止仍可用。配对、状态、停止、释放和动作入口共用这一步检查。

[摘要核对](evidence/ct75-http-zero/contracts.json)确认导出源码与仓库一致，相关控制／音频源码与 ct74 保持。

本轮没有修改 MCP 门禁、公开工具、语音角色、普通滴声策略、动作输出或距离阈值；也没有向实机发送畸形控制请求。本段为软件阶段记录；随后 ct75 已完成[部署及无动作 HTTP 检查](ct75-deployment.md)。

## 软件验证

[原生记录](evidence/ct75-http-zero/native.txt)通过 ASan／UBSan，直接执行实际 HTTP 处理器；ESP 传输与控制回调使用桩，检查拒绝时没有调用控制接口。新增覆盖操作名、键名、方向、草稿取消及 revision 键的零转义，1–8 个反斜线的奇偶层级、原始零字节、合法 Unicode 操作名，以及拒绝后的状态／停止通路。原有认证、所有动作分支、16 步草稿、分段接收、长度限制、会话释放与令牌轮换回归同时保留。

```sh
python3 firmware/esp32-audio/tests/run_mcp_tests.py --source build/xiaozhi-ct75-src
```

该命令包含实际 HTTP 处理器及 MCP／回执／播放匹配回归；需先按固件说明准备固定上游和 ct75 导出树。它不连接设备，也不证明 HTTP 网络时序或物理停止性能。完整构建与统一检查的摘要见 [verification-ct75.json](../../firmware/esp32-audio/verification-ct75.json)。

[十八组统一软件检查](evidence/ct75-http-zero/software-checks.json)全部通过，含 124 项 Python 测试；软件通过不增加模型语义、真人或物理成绩。完整应用为 2,721,488 字节，SHA-256 `6e6cf11e9ae1fd59e4280ec249495a8dc1602950a57e08b130ea44883714a8c8`。

## 部署边界

ct75 已获用户授权并完成[仅应用部署](ct75-deployment.md)，五类非动作畸形请求及合法查询／取消／空闲停止通过设备检查。畸形行走／效果请求未发送，不能泛化为所有设备分支覆盖。ct74 听感结果和用户选择跳过的三项保持原记录，本次不安排真人重测。
