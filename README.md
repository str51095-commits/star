# 光伏能源管理平台 ☀️

管理你的光伏电站，按 **日 / 月 / 年** 统计发电量、等效利用小时、收益和减排量。

- 纯 Python 标准库实现（无需 `pip install`），数据存储在本地 SQLite 文件
- 浏览器访问，支持电脑和手机，支持深色模式

## 快速开始

```bash
python3 run.py            # 默认 http://127.0.0.1:8000 ，数据库 solar.db
python3 run.py --port 9000 --db /path/to/my-solar.db
```

打开浏览器后：

1. **电站管理**：添加电站（名称、装机容量 kWp、上网电价、地址、并网日期）
2. **数据录入**：每天录入一次发电量（kWh），或用 CSV 批量导入逆变器/电表导出的数据
3. **概览**：查看今日 / 本月 / 本年 / 累计发电量，以及
   - **日发电量**：选择月份，看当月每天发了多少度电
   - **月发电量**：选择年份，看每月发电量，并与去年同期对比（同比）
   - **年发电量**：历年发电量对比

想先体验？在空白首页点 **生成演示数据**，会创建两个示例电站和约两年的模拟数据。

## 统计指标说明

| 指标 | 计算方式 |
|---|---|
| 发电量 | 录入的日发电量求和（1 kWh = 1 度电） |
| 等效利用小时 | 发电量 ÷ 装机容量 (kWp) |
| 收益 | 发电量 × 电站设置的单价（元/kWh） |
| CO₂ 减排 | 发电量 × 0.5703 kg/kWh（全国电网平均排放因子） |
| 节约标准煤 | 发电量 × 0.3 kg/kWh |

选择“全部电站”时，所有电站的发电量、容量、收益会合并统计。

## CSV 导入格式

每行 `日期,发电量kWh`，可带表头，日期支持 `2024-06-01` 或 `2024/6/1`：

```csv
日期,发电量
2024-06-01,210.5
2024-06-02,198.3
```

同一电站同一天重复导入会覆盖原值。“导出 CSV”可将数据导出（Excel 可直接打开）。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/stations` | 电站列表 / 新建 |
| PUT/DELETE | `/api/stations/{id}` | 修改 / 删除（连同其发电记录） |
| GET | `/api/records?station_id=&start=&end=` | 发电记录 |
| POST | `/api/records` | 录入或覆盖 `{station_id, day, kwh, note}` |
| DELETE | `/api/records/{id}` | 删除记录 |
| POST | `/api/import` | `{station_id, csv}` 批量导入 |
| GET | `/api/export?station_id=` | 导出 CSV |
| GET | `/api/stats/summary?station_id=` | 今日/昨日/本月/本年/去年/累计 |
| GET | `/api/stats/daily?month=YYYY-MM` | 某月每日发电量 |
| GET | `/api/stats/monthly?year=YYYY` | 某年每月发电量（含去年同期、同比） |
| GET | `/api/stats/yearly` | 历年发电量 |

`station_id` 省略时统计全部电站。

## 测试

```bash
python3 -m unittest discover -s tests
```
