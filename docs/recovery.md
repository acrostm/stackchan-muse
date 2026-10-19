# 原固件备份与恢复

已备份设备：ESP32-S3 revision 0.2，Flash 16 MiB。具体设备标识仅保留在本机诊断记录。
备份目录：`backups/factory-20261019/`，仅保存在本机，可能含配网和设备凭据，不上传。

`flash-a.bin` 与 `flash-b.bin` 各 16777216 字节，两次读取 SHA-256 一致：

`658dda9e044b480e910c052cf53c4151d00bb1f640a1fc56367b302db72f7651`

已完成完整 16 MiB 恢复写入，工具校验通过；重启观察到原固件 stack-chan 1.5.1、外设和 GUI 初始化，无 panic 或复位循环。此结果不替代原固件全部功能回归。
随后已刷入禁用舵机及自动 OTA 的 CoreS3 M1 探针，当前运行该探针。未修改 eFuse。

恢复前应再次核对目标 MAC、Flash 容量与备份校验和，确认串口没有其他程序占用。
恢复操作将覆盖设备当前 Flash；开发中只有需要回退并核验目标设备后才执行。

从项目根目录恢复的参考命令（本机已执行并验证）：

```sh
.venv/bin/python -m esptool --chip esp32s3 --port /dev/cu.usbmodem1101 write-flash 0 backups/factory-20261019/flash-a.bin
```

端口可能因重新连接变化。恢复后采集启动日志，检查无 panic/复位循环，并检查原功能。
原分区表在 `0x8000`，与 MuseChan 的 `0x10000` 不同；恢复必须用完整原始镜像，不能混用新旧分区表或只写原 app。
