# 中文快速使用说明（仅供准备论文匿名 Artifact）

## 1. 从独立文件夹开始

将压缩包解压到一个**新的**文件夹中。不要直接覆盖现有 `GUI_AHB_PAPER_REBUILD`，也不要复制它的 `.git` 目录。

```bash
cd ~/Desktop/guiagent-touch-typeb-paper
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
```

## 2. 在已经配好 NDK 的 Mac 上编译、推送

```bash
bash scripts/build.sh
bash scripts/deploy.sh
python3 -m guiagent_touch doctor
```

只测试一个安全的点击位置：

```bash
python3 -m guiagent_touch probe-tap 440 204 --dwell 100 --yes
```

**注意：**上面这条会真的触摸手机；先确认当前页面和坐标安全。未经测试的 Android 设备可能没有 `/dev/uinput` 权限。本实验程序仅支持 1080×2400 画面。

## 3. 建立新的、与原研究仓库无关的 Git 历史

执行之前先检查 GitHub 公开仓库是否符合目标会议双盲规定。请勿使用带个人身份的信息、旧 `.git` 历史或任何私密手机日志。

```bash
git init -b main
git config --local user.name "Anonymous Artifact"
git config --local user.email "anonymous@example.invalid"
python3 scripts/check_release.py
git add .
git status --short
git diff --cached --name-only
git commit -m "Initial reproducibility artifact: Android Type-B input layer"
git log -1 --format=fuller
```

**到这里不会上传 GitHub。** 审核通过之后，在目标账号中手工创建一个空仓库，再执行：

```bash
git remote add origin https://github.com/REPLACE_ACCOUNT/REPLACE_REPO.git
git push -u origin main
```

上面示例中的 `REPLACE_ACCOUNT/REPLACE_REPO` 必须替换为你最终决定用于论文 Artifact 的仓库；不要把这里的占位符当成真实网址。即使提交作者名写为 Anonymous，**仓库的拥有者以及推送账号仍然可能暴露身份**。

## 4. 双盲链接

一种常见方式是将审查过的仓库交给 https://anonymous.4open.science/ 生成只读匿名镜像；在论文中按照会议规定放镜像链接，而不是可追溯到个人的 GitHub 原始地址。要亲自打开镜像检查代码、图片、文件名和 README，镜像不保证万无一失。

## 5. 这个初版没有包含什么

没有包含 Frozen V3 权重、AutoGLM API 客户端、完整原始实验日志、真实手机截图或论文实验结果。它是 **输入执行/轨迹采集层**，不是论文全部实验的完整复现包。后续应当在确认授权和去标识化以后，再加入评估适配器与固定实验配置。
