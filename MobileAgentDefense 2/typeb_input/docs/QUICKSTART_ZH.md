# Android Type-B 中文快速使用说明

本目录是 Android uinput Type-B 输入执行和 getevent 轨迹采集模块，不是完整的 Defense 模型。

## 测试

```bash
cd typeb_input
python3 -m unittest discover -s tests -v
```

GitHub Actions 会在 Linux 上完成 C 语法检查，不需要在 Mac 安装 Docker。

## 在已经配置好 Android NDK 的 Mac 上构建

```bash
cd typeb_input
bash scripts/build.sh
bash scripts/deploy.sh
python3 -m guiagent_touch doctor
```

## 单个安全动作和观测

```bash
python3 -m guiagent_touch probe-tap 440 204 --dwell 100 --yes
python3 -m guiagent_touch probe-swipe 540 1550 540 850 --duration 450 --yes
```

以上命令会真正触碰设备，请确保设备归你控制、位置安全，并且 ADB shell 对 `/dev/uinput` 有合法权限。当前原型只支持 1080×2400。

## 路径关系

- `native/uinput_typeb_agent_compat.c`: Linux uinput 实现
- `guiagent_touch/__main__.py`: Python/ADB 封装
- `guiagent_touch/events.py`: 过滤、计数和对齐 getevent
- `scripts/build.sh` 和 `scripts/deploy.sh`: 生成 Android 可执行文件和部署
- `tests/test_events.py`: 测试事件完整性

完整 V3 frozen defense、作者权重和评价脚本在仓库其他子目录；当前 staging 包不等于完整可复现发布版。
