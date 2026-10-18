# 硬件盘点

芯片已确认 ESP32-S3 revision 0.2、16 MiB Flash，quad 数据线。
原固件备份包含 CoreS3 / StackChan / SCSCL 标记，重启日志包含 StackChan。
舵机零位和机械安全范围仍待实机确认。
不能由 `303a:1001` 推断为 CoreS3；它也用于其他 ESP32 系列设备。

待记录：芯片、Flash 容量、Core 型号、屏幕版本、舵机型号及 ID、原固件版本、yaw/pitch 零位与安全范围。
备份置于根目录 `backups/`（忽略入库，权限限制），保留 SHA-256 和实际字节数。

已保存两份完整原始 Flash：`backups/factory-20261019/flash-a.bin` 与 `flash-b.bin`。
两份各 16777216 字节且 SHA-256 一致，详见同目录 manifest.json。
**尚未做恢复写入测试。** 备份后设备已恢复运行原固件。
