#!/bin/bash
# macOS 双击启动 / Linux 运行 ./start.command
cd "$(dirname "$0")"
# 固德威自动同步（可选）：去掉下面两行开头的 # 并填写 SEMS 账号
# export GOODWE_ACCOUNT=你的账号
# export GOODWE_PASSWORD=你的密码
exec python3 run.py
