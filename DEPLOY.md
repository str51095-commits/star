# 部署到云服务器

部署后可以随时用手机或电脑访问平台，固德威数据 24 小时自动同步，不用一直开着自己的电脑。

## 1. 准备一台云服务器

- 推荐 **阿里云 / 腾讯云「轻量应用服务器」**，最低配置（1 核 1G 或 2 核 2G）就够用。
- 系统选 **Ubuntu 22.04 或 24.04**（自带 Python 3，无需安装其他软件）。
- 地域选离你近的；只用 IP 访问时不需要备案。

## 2. 把代码传到服务器并安装

登录服务器（云控制台的「远程登录」按钮，或 `ssh root@服务器IP`），执行：

```bash
apt update && apt install -y git
git clone -b claude/solar-energy-management-platform-4nc0xv https://github.com/str51095-commits/star.git solar-ems
cd solar-ems
sudo bash deploy/install.sh
```

> 仓库是私有的话，`git clone` 会要求输入 GitHub 用户名和 [个人访问令牌](https://github.com/settings/tokens)；
> 也可以在自己电脑上下载 ZIP，用云控制台的文件上传功能传到服务器后解压。

安装时会让你设置**登录密码**。完成后平台会在后台运行，并且开机自动启动。

## 3. 放行端口

在云服务器控制台找到 **防火墙 / 安全组**，添加规则：允许 **TCP 8000** 端口。

然后浏览器访问 `http://服务器公网IP:8000`，输入密码登录。

## 4. 开启固德威自动同步

```bash
sudo nano /etc/solar-ems.env      # 去掉 GOODWE_ACCOUNT / GOODWE_PASSWORD 前面的 #，填写 SEMS 账号
sudo systemctl restart solar-ems
```

再到平台「电站管理」里填写固德威电站 ID 即可。

## 日常维护

| 操作 | 命令 |
|---|---|
| 查看运行状态 | `systemctl status solar-ems` |
| 查看日志 | `journalctl -u solar-ems -f` |
| 重启 | `sudo systemctl restart solar-ems` |
| 修改密码 / 配置 | `sudo nano /etc/solar-ems.env` 后重启 |
| 升级到新版本 | `cd solar-ems && git pull && sudo bash deploy/install.sh` |
| 备份数据 | `sudo sqlite3 /var/lib/solar-ems/solar.db ".backup /root/solar-backup.db"` 或直接复制该文件 |

## 安全说明

- 平台对外开放时**必须设置密码**，否则拒绝启动。密码连续输错 8 次会锁定 5 分钟。
- 用 `http://IP:8000` 访问时，数据（包括登录密码）在网络上是**未加密**传输的。
  如果有域名，建议加 HTTPS：
  - 国内服务器绑定域名需要先完成 **ICP 备案**；香港/海外服务器不需要。
  - 最简单的方式是安装 [Caddy](https://caddyserver.com/docs/install)，然后运行
    `caddy reverse-proxy --from 你的域名 --to 127.0.0.1:8000`（会自动申请免费证书），
    并在 `/etc/solar-ems.env` 中打开 `SOLAR_TRUST_PROXY=1` 和 `SOLAR_SECURE_COOKIE=1`。
    启用 HTTPS 后可在安全组中关闭 8000 端口，只开放 80/443。

## 使用 Docker（可选）

服务器能正常拉取 Docker Hub 镜像时（国内服务器需先配置镜像加速），也可以用 Docker：

```bash
cp .env.example .env && nano .env      # 填写密码等
docker compose up -d                   # 访问 http://服务器IP:8000
docker compose --profile https up -d   # 已在 .env 填写 DOMAIN 时，自动启用 HTTPS
```

数据保存在 `./data/solar.db`。
