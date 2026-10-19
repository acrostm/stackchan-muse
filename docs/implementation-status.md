# 实施记录 · 2026-10-19

## 基线

MuseChan: https://github.com/Tjtelenda/musechan/tree/4eab881f95f849fe823b0645f7bf027770f45a2a

ESP-IDF v6.0.1: `8c19b156084a0753687347cca1f5355782893533`。
已读取 `firmware/esp32/AGENTS.md`。尚未修改固件行为。

## 实际模块路径

| 能力 | 源码 | 当前判断 |
|---|---|---|
| 配对、网络、设备能力目录 | `firmware/esp32/main/app.c` | 复用官方链路；账号能力待实测 |
| 录音提交、回复、取消、TTS | `firmware/esp32/components/muse/muse_chat_session.cpp` | 存在 `record_note`、`start_tts`、`local_tts_fetch`、turn cancel |
| 音频输出与状态 | `firmware/esp32/components/muse/` | 必须实机确认播放完成及触摸停止 |
| CoreS3 驱动 | `firmware/esp32/components/muse/boards/board_m5stack_stackchan.c` | 屏幕、触摸、扬声器、麦克风复用 |
| 头部及底座 | `firmware/esp32/components/muse/boards/stackchan_head.c` | 上游零位写死，缺每设备校准；不可直接按默认零位验收 |
| 触摸与姿态反应 | `firmware/esp32/components/muse/boards/stackchan_pet.c` | 与动作仲裁共同审查 |
| 相机 | 上游可选 camera capture | 上游明确声明帧尚不可用；首版不得宣称看得见 |

本地 TTS 审计：同步 HTTP 最长阻塞 45 秒；700 限制按字节计数，可能截断 UTF-8；512 KiB 缓冲满时丢弃数据仍可能判成功。需要修复并测试中文、超长音频、取消与超时，再接入提供商。

## 设备

检测到 `/dev/cu.usbmodem1101`，USB VID:PID `303a:1001`，Espressif 原生 USB。
描述不能单独确认 CoreS3、Flash 容量或舵机型号。
只读日志输出包含 `SystemInfo: free sram`，未取得硬件型号。
用户确认有 Muse 开发者模式、SDK token 和豆包语音 API。
后续已通过 esptool 确认 ESP32-S3 revision 0.2、16 MiB Flash，quad 数据线。
已读两次完整 Flash，两个文件 SHA-256 一致：
`658dda9e044b480e910c052cf53c4151d00bb1f640a1fc56367b302db72f7651`。
文件位于 `backups/factory-20261019/`，每份 16777216 字节，0600 权限。
尚未做恢复写入测试。读取后已重启回原固件，启动日志观察到 StackChan 标记。
备份的分区表位于 0x8000；ota_0 项目 `imu_gimbal` 版本 `874f01a`，ota_1 项目 `stack-chan` 版本 `1.5.1`。
备份中同时观察到 CoreS3 / StackChan / SCSCL 字符串；这不能确定每台舵机的机械零位。
尚未刷写或擦除设备。

## 测试

执行上游完整 unittest：138 项，5 errors，4 skipped，失败退出。
错误为缺 CMake（三个子用例）与未下载 cJSON（两个测试类初始化）。
这是未通过的测试基线，不能报告为全部通过。

构建环境下载遇到 GitHub / PyPI TLS EOF，多次重试；ESP-IDF 主仓已到位，子模块及 Python 工具仍需完成。尚未编译固件。

后续：国内镜像完成 esptool/CMake/Ninja 安装，ESP-IDF Python 环境及 Xtensa 编译器已安装。
补齐 CMake 后重跑上游 138 项测试：2 errors（缺 cJSON），3 skipped。其余完成；整体仍失败。
完整固件构建尝试在 IDF 子模块初始化阶段失败，尚未进入编译。
本机代理先尝试 7890（拒绝连接），用户更正为 7897；7897 经 HTTPS 探针可访问 GitHub，Git 下载仍间歇 TLS 失败。

新增主机代码：`companion/doubao.py` 及带认证的 `companion/tts_server.py`。
真实豆包短句合成成功，音频 30957 字节；系统音频解析确认 MP3、24 kHz、单声道、64 kbps、约 3.864 秒。
探针识别到合法 `data:null` 统计/结束事件，已加入回归测试。
项目自测 12 项通过，包含真实回环 HTTP 集成测试；不等于设备播放通过。
桥接服务尚未对局域网启动；设备端 TTS 取消和缓冲问题尚未修改。

用户后续要求不经代理端口，已停止代理下载任务并清除本次下载/构建命令的代理环境。
直连取得 cJSON v1.7.19 及 ESP32-S3 核心库的指定版本（包括 mbedTLS）。
补齐依赖后上游主机测试：143 项，141 passed、2 skipped；配对真实密码学测试另设 IDF_PATH 重跑通过（1 项）。
新增 `tools/build_firmware.py` 使用绝对构建/配置路径，默认不嵌入 token，也不刷机。

StackChan 基线完整编译通过：签名 app 大小 `0x221000`，4 MiB app 槽余量约 47%，hash 见 `baseline-build.json`。
已下载的 managed components 精确版本见 `firmware-dependencies.lock.yml`。
主机完整环境重跑上游测试：143 项，1 skipped（Noise Core 需要主机 PSA Crypto 开发库），其余通过；配对握手及 Python 密码学向量已运行。
正在准备禁用舵机驱动的 CoreS3 + text replies 设备能力探针；其首次配置因组件注册表连接失败退出，已直连重试。尚未刷写。
该探针第二次直连构建仍在组件注册表访问阶段失败，未生成可刷写探针。
当前可编译的 StackChan 基线未嵌入账号 token，且未完成音频、舵机保护和实机验收，不能交付为首版。
所有本轮构建/下载任务均已结束；设备仍运行原固件，未部署桥接服务。

## M1 实验与发布门槛

1. 识别芯片/Flash/运行固件及底座，备份完整 Flash 两次比对 SHA-256，记录恢复命令；备份含凭据，仅存本机。
2. 固定依赖并干净编译 StackChan 配置，检查分区大小。
3. Muse 配对：单轮中文语音→文字；记录事件顺序和 turn 关联。
4. 验证共享偏好、会话历史、只读工具、长任务与断网重连；未观测的能力标 unknown。
5. 豆包真实鉴权及音色探针，然后验证真实扬声器输出。
6. 取消、超时、旧回复、重复事件、401/429、断网；字幕和错误状态可恢复。
7. 校准、限位、速度与紧停验证后才启用头部动作。
8. 20 轮中文问答及 2 小时稳定性。通过后才提供试刷候选及具体已知限制。

豆包官方接口参考：https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http?lang=zh
当前新接口使用 X-Api-Key；用户凭据若为 App ID / Access Token，需要核实对应旧接口，不能混用。

## 主线恢复与主动播报需求

CI 修复 PR #3 的最终提交 `5fc0e90d9e83ecfb467edd42f402ab1125ec20e1`：云端两种板型、打包、项目测试、143 项上游测试（零跳过）及 UI 模拟器均通过，官方 Codex 原生结果 completed / no findings。main 保持保护；首次门禁引导的手动状态发布被自动审批拒绝，未执行，PR 尚未合并。

无舵机的 CoreS3 账号探针已成功编译，静态配置确认使用 CoreS3 驱动、text replies，未启用 StackChan 头部驱动及不可逆 eFuse 选项。账号产物只留本机；未刷机、未配对、未宣称语音或主动消息已可用。

已将中文 TTS 的 700 字节截断改为最多 700 个完整 UTF-8 码点，并验证 JSON 转义、非法编码及容量不足拒绝，27 项项目测试通过。CoreS3 与 StackChan 重新编译均通过，StackChan app 为 0x221000、分区余量 47%。同步 HTTP 取消和音频溢出等剩余问题仍需处理。

新增主动消息、计划任务结果的提示音及朗读需求，详见 `proactive-messages.md`。源码已确认订阅流长期存在，但闲置状态直接过滤事件；服务端投递范围必须配对后逐类实测，尚未实现后台收件箱或通知播报。

## 实机更新：恢复、探针启动及扬声器

本节更新前述历史记录：PR #3 与 #1 已正常合并。PR #3 的一次 Bootstrap 状态经用户单独明确授权后发布；main 保护未关闭。后续 PR 使用 main 上的正式门禁。

重新读取完整 Flash，与两份原备份一致。实际写回完整原镜像，写入哈希验证通过；重启观察到 stack-chan 1.5.1 正常初始化，未见 panic。随后刷入 CoreS3 文字回复探针，启动识别 8 MiB PSRAM，进入未配对广播，状态 Ready to pair。探针禁用自动 OTA，不编译头部驱动，不启用不可逆 eFuse 选项。账号镜像和原始日志只保留本机。

通过设备内置 MP3 自测，解码 153 帧、24 kHz、约 3.67 秒；用户明确反馈“听到了，声音正常”。这验证扬声器播放，不代表豆包语音或 Muse 问答闭环通过。项目 27 项测试再次通过。

当前 M0 已有备份、恢复写入与启动证据；M1 已刷入并启动，等待手机配对与真实语音往返。M2 仅有豆包独立合成和内置音频播放等部分证据；中文回复播放、取消与溢出处理、表情和头部校准未完成。M3–M5 的唤醒、视觉、主动消息播报及长期稳定性未完成。尚未执行 20 轮对话和 2 小时稳定性验收，release_ready 仍为 false。

用户已完成手机配对，设备确认 paired 与 Wi-Fi connected。第一次串口文字连通性测试返回 CAN'T REACH MUSE；设备日志为账户 API 连接超时。用户确认仅 Mac/手机启用代理，路由器未为设备提供海外网络路径。Mac 无凭据探测官方 API 可达；设备对话尚未通过。

PR #4 官方审查指出字幕累积的 1024 字节缓冲可能在 UTF-8 字符中间截断，使严格 JSON 编码拒绝整段。已将缓冲扩大到可容纳 700 个四字节码点，追加时只保留完整码点，首次截断后停止追加以保持原文前缀；新增流式中文/emoji 和各容量边界回归。

## 网络中继与第一轮真实 Muse 往返

PR #1–#4 已在全部 CI 与对应当前提交的官方 Codex 审查通过后正常合并。

新增可选 Mac 固定目标 TLS 透传中继，设备验证官方证书，不解密内容；启动时出现 TLS 握手失败并重试，之后账户请求成功，设备状态变为 Muse Connected / Link Online。串口发送无个人信息的测试消息，收到真实 Muse 的预期回复“设备连接成功”，工具正常结束。这只验证文字输入的账户/会话往返，不替代麦克风输入、中文 TTS 或完整语音验收。

更新应用前已备份配对后的 NVS，仅写应用分区，配对与 Wi-Fi 保留。中继仍依赖 Mac 常开及可用网络路径，当前探针仍禁用舵机和自动 OTA。官方 PR #5 审查指出第二账户客户端也需路由，以及关闭构建参数时必须清理旧中继配置；两项已修复，新增配置切换回归，33 项项目测试通过。

## Muse StopWatch design port

Ported the reference adapter's practical controls: a two-second physical PTT
guard, no upload of short/cancelled notes, persistent browser setup PIN, blank
secret fields that preserve saved credentials, per-SSID SOCKS5/Clash routing,
and an idle final-message notification inbox.

Hardware evidence: a 0.5 s press produced no `voice note` request. The setup AP
started as `Muse-Setup-AF9011`; Mac temporarily joined it, loaded the page and
session successfully, and submitted Muse, Doubao and proxy settings with HTTP
202. The page then closed. The saved Doubao configuration made device-side
`sw.preview` return `result=ok`.

Network evidence: the device completed SOCKS5 handshakes to the saved LAN
proxy. The current Clash node then closed the TLS connection before the official
certificate was validated; direct Mac probes through both HTTP and SOCKS have
the same failure. This is tracked as an external proxy-node issue, not counted
as a successful Muse voice round trip.

Latest local project suite: 47 tests passed. The new idle notification queue is
bounded to four messages, deduplicates 32 recent IDs, preserves complete UTF-8,
and only accepts terminal assistant/text events. Real scheduled-task delivery
still needs a working Muse connection and an actual account-side event.

The final review pass found two race/transport edge cases. Each physical press
now carries its own bounded turn id, so a cancelled recording remains
cancelled even if the next press arrives while its tail is still being
validated. Its small shared state uses a short non-preemptive FreeRTOS critical
section, avoiding the priority inversion a spin lock could cause on the
single-core ESP32-C6. The ListSpeakers response reader now drains cached body
bytes before trusting ESP-IDF's completion flag, which fixes small responses
that arrive together with the headers.

## Final voice and notification evidence

The voice-note request now asks Muse for text output. A synthetic Chinese utterance
played at the microphone produced a 6.60 s note, a server acknowledgment, a
21-character assistant reply, and 1.80 s of PCM playback. The complete turn took
9.83 s. This establishes microphone input, Muse reply and device speech as one
working chain on the attached hardware.

The fixed device TTS self-test played 3.97 s of PCM. An injected proactive
notification was accepted by the bounded inbox, woke the speaker path, and
played 3.01 s of TTS. No panic or reboot occurred. These tests do not prove that
Muse delivers arbitrary phone messages or scheduled-task results; that requires
real account events and remains to be observed.

## Safe conversational head motion

The StackChan head now follows the per-unit NVS keys used by M5Stack's BSP
(`servo/zero_pos_1` and `servo/zero_pos_2`). At boot it reads present position
before torque is enabled. Factory default zeroes are not accepted as user
calibration: motion also requires the explicit `servo/muse_cal=1` marker that
only `head.calibrate` writes after reading both real servo positions. If that
marker, the zeroes or feedback are missing, the screen, voice and camera paths
continue and motion reports unavailable rather than moving against guessed
values.

One motion task owns both servos. Finished reply text selects only small local
gestures (nod, affirmative nod, thinking tilt, apology shake or happy lift);
there is no extra model call. A critically damped 50 Hz trajectory enforces the
BSP angle/raw limits, command priorities let pet and explicit commands interrupt
expressive motion, and torque is released after 250 ms at rest. A face tap,
head pat, face-down pose or power-off cancels motion immediately. `head.stop`,
`head.status`, `head.calibrate` and `head.look=YAW,PITCH` are available on the
serial console so an operator can centre the head by hand and save the real
position without boot-time movement.

The StackChan firmware builds at `0x221000` bytes with 47% of its app slot free.
The 47-test project suite and UI-independent motion planner pass. Per-unit
calibration, physical limit observation, audible/visual gesture capture and
long-duration servo stability still require the attached robot and are not
claimed as hardware-verified.
