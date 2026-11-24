# 光伏方案设计

员工登录网页，填写客户和项目数据，一键导出润恒城模版格式的 Word 方案。

- **项目类型**：工商业、户用
- **商业模式**：投资方全额投资（合同能源管理，EMC）、业主自投
- **自动计算**：装机容量、组件和逆变器数量、25 年逐年发电量、自发自用电量、节省电费或收益、投资回收期、减排量
- **自动出图**：月用电量柱状图、用电与发电匹配图、收益测算图（填了用电数据才有前两张）
- **历史方案**：服务器只保留最近 3 份方案（每份约 6.7MB），更早的自动删除；可以重新下载，也可以「复制并修改」。
  想改保留份数，在 `/etc/systemd/system/pvplan.service` 里加一行 `Environment=PVPLAN_KEEP=5`
- **账号**：管理员在「设置」里添加员工账号、修改公司信息（编制单位等）

## 安装到服务器（腾讯云 Ubuntu）

在腾讯云终端里先粘贴 `cd ~` 回车，再粘贴下面这一行回车：

```bash
rm -rf pvplan-src && curl -fL --retry 3 --connect-timeout 20 https://github.com/str51095-commits/star/archive/refs/heads/claude/busy-brown-t45kup.tar.gz -o pvplan.tgz && mkdir -p pvplan-src && tar xzf pvplan.tgz -C pvplan-src --strip-components=1 && cd pvplan-src && sudo bash deploy/install.sh
```

装完会显示网址和管理员初始密码。网址是 `http://服务器IP:8600`。
如果打不开，到腾讯云控制台的「防火墙」（轻量应用服务器）或「安全组」（云服务器）里放行 **TCP 8600**。

以后升级也用同一行命令，账号和历史方案都会保留。
光伏能源管理平台不受影响，两个程序各用各的端口。

常用命令：

```bash
sudo systemctl status pvplan            # 查看运行状态
sudo journalctl -u pvplan -n 50         # 查看日志
sudo cat /var/lib/pvplan/admin-password.txt   # 查看管理员初始密码
cd /opt/pvplan && sudo -u pvplan PVPLAN_DATA=/var/lib/pvplan venv/bin/python -m pvplan passwd admin 新密码   # 忘记密码时重置
```

数据都在 `/var/lib/pvplan`（数据库和生成的 Word 文件），备份这个目录即可。

## 目录说明

| 路径 | 作用 |
| --- | --- |
| `pvplan/calc.py` | 全部计算（发电量、收益、回收期等） |
| `pvplan/report.py` | 把计算结果填进模版生成 Word |
| `pvplan/charts.py` | 三张图表 |
| `pvplan/assets/template.docx` | 方案模版（客户数据已换成「示例」） |
| `pvplan/app.py` | 网页（登录、填写、列表、设置） |
| `tools/prepare_template.py` | 换新模版时用：把原始方案处理成程序用的模版 |
| `deploy/install.sh` | 服务器一键安装 / 升级 |

## 计算口径

- 首年发电量 = 装机容量 × 首年等效利用小时数（默认 1400h）× (1 − 首年衰减)，之后每年按「每年衰减」递减
- 月度发电按北方地区典型月度分布拆分（来自原模版的月度发电曲线）
- 合同能源管理：年节省电费 = 自发自用电量 × (现行电价 − 光伏结算电价)
- 业主自投：年净收益 = 自用电量 × 现行电价 + 上网电量 × 上网电价 − 运维费；回收期为静态回收期
- 减排量 = 累计发电量 × 电网排放因子（默认 0.5306 kgCO₂/kWh）

## 本地开发

```bash
pip install -r requirements.txt pytest
python3 -m pvplan adduser admin 管理员 test123456 --admin
python3 -m pvplan serve --port 8600
python3 -m pytest -q tests
```
