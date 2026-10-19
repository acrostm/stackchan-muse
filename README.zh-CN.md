# MuseStack — StackChan × Muse

[简体中文](README.zh-CN.md) · [English](README.md)

让基于 CoreS3 的 StackChan 成为你现有 Muse 的实体终端：语音对话、中文语音回复、屏幕表情和受控头部动作。Muse 继续负责推理及工具执行，本项目不使用另一模型冒充你的 Muse。

**当前是开发快照，尚不是可直接刷写的成品。已刷入并启动无舵机的 CoreS3 文字回复探针，用户确认内置音频播放正常；Muse 配对已通过，对话闭环受设备网络路径阻塞。** 已验证与未验证能力分别记录在[能力清单](docs/capabilities.json)和[实施记录](docs/implementation-status.md)。

## 当前状态

| 功能 | 已有证据 | 待完成 |
|---|---|---|
| 备份恢复 | 两份完整 16 MiB 备份一致；全量恢复写入校验及原固件启动通过 | 原固件全部功能回归 |
| 固件构建 | ESP-IDF 6.0.1 下基线编译通过，app 分区余量约 47% | CoreS3 探针已启动，识别 8 MiB PSRAM；待验证对话 |
| 主机测试 | 本机上游 143 项、1 项跳过；新增 28 项通过 | 云端 CI 结果独立记录 |
| 中文语音 | 豆包真实合成输出 24 kHz 单声道 MP3 | 内置 MP3 实机播放通过；待验证豆包设备播放、取消、超时 |
| Muse 接入 | 保留官方 SDK 与配对链路 | 配对、语音闭环、个人上下文和工具能力验证 |
| 表情及头部 | 上游驱动存在 | 状态接线、校准、限位与调度 |
| 摄像头及周边感知 | 上游取帧仍不可用 | 后续开发，目前不宣称具备视觉 |

唤醒、跟踪、全双工及任务通知尚未实现验收。[主动消息与计划任务播报](docs/proactive-messages.md)已纳入需求，投递范围仍待真实 Muse 事件验证。

## 目录与来源

`firmware/` 保存 MuseChan 的源码快照，具体提交见[上游锁定记录](docs/upstream-lock.json)，保留原许可证；没有嵌套 Git 仓库。`companion/` 是豆包适配及可选本地桥接；`tools/` 是构建和备份工具；`tests/` 是新增测试；`docs/` 保存开发计划、证据、依赖及恢复说明。

`.private/`、`backups/`、`.toolchains/`、`build-*/` 仅留本机，不进入版本库。

## 开发起步

要求 Python 3.10+、C/C++ 编译器及 **ESP-IDF v6.0.1**。本机工具链布局见[开发说明](docs/development.md)。普通 IDF 环境激活后：

```sh
python3 tools/init_config.py
python3 -m unittest discover -s tests -v
cd firmware/esp32
idf.py -B build-stackchan -DIDF_TARGET=esp32s3 \
  -DSDKCONFIG="$PWD/build-stackchan/sdkconfig" \
  -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;devices/sdkconfig.muse;devices/sdkconfig.muse-m5stack-stackchan" build
```

只在 `.private/config.json` 填写你自己的 Muse token 和豆包凭据。初始化工具不会覆盖已有文件。上述基线不含账号 token，不能作为已配好账号的成品。使用项目本机工具链时，`python3 tools/build_firmware.py --with-token` 会嵌入本机 token，相关产物必须保密。

`python3 -m companion.tts_server` 默认只监听回环地址，参见[桥接说明](companion/README.md)。机器人使用桥接时暂时需要一台可访问主机；完全独立语音仍需集成。

## 质量门禁和交付

PR 和 main 推送检查仓库及凭据、项目测试、上游主机测试、UI 模拟器，以及 StackChan/CoreS3 两种无账号固件的编译和分区大小。CI 不刷硬件、不调用付费 API、不配对账号、不接收个人凭据。构建包附带校验和及源码来源。

发布必须有匹配源码树的实机报告、CI 全部成功、人工明确确认，并经过 `firmware-release` 环境。流水线只创建**草稿发布**；人工记录不等于自动证明硬件无故障。规则见[CI 与发布说明](docs/ci-release.md)。

## 硬件和隐私

先识别板型及舵机、保留校验过的原固件，再校准和启用运动。普通开发不启用不可逆 eFuse。桥接服务不暴露公网，局域网 HTTP 不提供加密。原始录音、图片、账号令牌、Wi-Fi 凭据及完整设备备份都不得进入 Git 或 CI 产物。

## 贡献与许可

参见[贡献规范](CONTRIBUTING.md)、[安全说明](SECURITY.md)、[恢复手册](docs/recovery.md)和[来源声明](NOTICE)。代码使用 [Apache-2.0](LICENSE)，第三方文件保留各自许可。上游 Jollybot 素材有单独条款，**未在本项目重新授权**。这是独立个人项目，并非 Meta 或 M5Stack 官方产品。
