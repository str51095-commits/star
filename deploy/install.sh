#!/usr/bin/env bash
# 光伏方案设计 —— 一键安装 / 升级
# 用法：在解压后的目录里执行  sudo bash deploy/install.sh
# 可选：PVPLAN_PORT=8600（默认端口）
set -euo pipefail

PORT="${PVPLAN_PORT:-8600}"
APP=/opt/pvplan
DATA=/var/lib/pvplan
SRC="$(cd "$(dirname "$0")/.." && pwd)"
PIP_MIRROR="https://mirrors.cloud.tencent.com/pypi/simple"

if [ "$(id -u)" != "0" ]; then echo "请用 root 运行：sudo bash deploy/install.sh"; exit 1; fi
echo "==> 1/5 安装系统依赖（Python、中文字体）"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || true
apt-get install -y -qq python3 python3-venv python3-pip fonts-noto-cjk >/dev/null

echo "==> 2/5 复制程序到 $APP"
id pvplan >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin pvplan
mkdir -p "$APP" "$DATA"
rm -rf "$APP/pvplan"
cp -r "$SRC/pvplan" "$SRC/requirements.txt" "$APP/"
chown -R pvplan:pvplan "$DATA"

echo "==> 3/5 安装 Python 依赖（使用腾讯云镜像）"
[ -x "$APP/venv/bin/python" ] || python3 -m venv "$APP/venv"
pipi() {  # 先用腾讯云镜像，连不上再用官方源
  "$APP/venv/bin/pip" install -q --retries 1 --timeout 20 -i "$PIP_MIRROR" "$@" 2>/dev/null \
    || "$APP/venv/bin/pip" install -q "$@"
}
pipi -r "$APP/requirements.txt"

run() { sudo -u pvplan env PVPLAN_DATA="$DATA" MPLCONFIGDIR="$DATA/.mpl" HOME="$DATA" "$APP/venv/bin/python" "$@"; }
cd "$APP"
rm -rf "$DATA/.mpl"   # 让图表重新识别中文字体

echo "==> 4/5 检查管理员账号"
NEWPW=""
if ! run -c "import sqlite3,sys,os; from pvplan import app; app.init_db(); c=sqlite3.connect(app.DB_PATH); sys.exit(0 if c.execute('select count(*) from users').fetchone()[0] else 1)"; then
  NEWPW="$(python3 -c 'import secrets,string; a=string.ascii_letters+string.digits; print("".join(secrets.choice(a) for _ in range(10)))')"
  run -m pvplan adduser admin 管理员 "$NEWPW" --admin >/dev/null
  echo "admin / $NEWPW" > "$DATA/admin-password.txt"; chmod 600 "$DATA/admin-password.txt"
fi

echo "==> 5/5 启动服务（端口 $PORT）"
if ss -ltnp 2>/dev/null | grep -q ":$PORT " && ! systemctl is-active --quiet pvplan; then
  echo "端口 $PORT 已被其他程序占用，请换一个端口：PVPLAN_PORT=8601 sudo -E bash deploy/install.sh"; exit 1
fi
cat > /etc/systemd/system/pvplan.service <<UNIT
[Unit]
Description=光伏方案设计
After=network.target

[Service]
User=pvplan
WorkingDirectory=$APP
Environment=PVPLAN_DATA=$DATA
Environment=MPLCONFIGDIR=$DATA/.mpl
ExecStart=$APP/venv/bin/python -m pvplan serve --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable -q pvplan
systemctl restart pvplan
ok=0
for i in $(seq 1 20); do
  if curl -s -o /dev/null "http://127.0.0.1:$PORT/login"; then ok=1; break; fi
  sleep 1
done
if [ "$ok" != 1 ]; then echo "启动失败，请把下面的日志截图发给我："; journalctl -u pvplan -n 30 --no-pager; exit 1; fi

IP="$(curl -s --max-time 3 http://metadata.tencentyun.com/latest/meta-data/public-ipv4 || true)"
[ -n "$IP" ] || IP="你的服务器公网IP"
echo
echo "================================================"
echo " 安装完成！浏览器打开： http://$IP:$PORT"
if [ -n "$NEWPW" ]; then
  echo " 管理员账号：admin"
  echo " 初始密码：  $NEWPW   （登录后请在右上角修改）"
else
  echo " 已是升级安装，账号和历史方案都保留不变"
fi
echo " 如果打不开：到腾讯云控制台 → 防火墙/安全组，放行 TCP $PORT 端口"
echo "================================================"
