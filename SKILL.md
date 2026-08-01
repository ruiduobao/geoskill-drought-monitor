---
name: drought-monitor
description: 'Calculate SPI (Standardized Precipitation Index) and SPEI (Standardized description: 'Calculate SPI (Standardized Precipitation Index) and SPEI (Standardized  Precipitation Evapotranspiration Index) from NASA POWER API data for  drought monitoring. Supports multiple timescales (1-24 months), drought  classification, and trend analysis.  '
---

# drought-monitor

Calculate SPI (Standardized Precipitation Index) and SPEI (Standardized Precipitation Evapotranspiration Index) for drought monitoring using NASA POWER API precipitation data.

## Features

- **SPI Calculation**: Gamma distribution fitting + inverse normal transform
- **SPEI Calculation**: Water balance (P - PET) with log-logistic fitting
- **Multiple Timescales**: 1, 3, 6, 12, 24 months
- **Drought Classification**: 7 levels from extreme drought to extremely wet
- **Trend Analysis**: Linear regression on SPI time series
- **Local CSV Mode**: Offline processing with pre-downloaded data
- **NASA POWER Integration**: Auto-fetch global precipitation data (no API key)

## Usage

```bash
# Calculate 3-month SPI for a location
python scripts\drought-monitor.py spi --lat 39.9042 --lon 116.4074 --start 2020-01-01 --end 2023-12-31 --scale 3

# Calculate 12-month SPEI from local water balance CSV
python scripts\drought-monitor.py spei --input water_balance.csv --scale 12

# Generate drought report
python scripts\drought-monitor.py report --input spi_3m.csv --output report.json
```

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--lat` | Latitude (-90 to 90) | Required |
| `--lon` | Longitude (-180 to 180) | Required |
| `--start` | Start date (YYYY-MM-DD) | Required |
| `--end` | End date (YYYY-MM-DD) | Required |
| `--scale` | SPI/SPEI timescale in months | 3 |
| `--input` | Local CSV for offline mode | None |
| `--output` | Output file path | Auto-generated |

## Installation

```bash
pip install requests>=2.28.0 tqdm numpy scipy pandas
# Or: pip install -r scripts/requirements.txt
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `scipy` | Gamma/log-logistic distribution fitting |
| `numpy` | Numerical computation |
| `pandas` | CSV I/O and time series handling |
| `requests` | NASA POWER API calls |
| `tqdm` | Progress bars |

## Data Source

- **NASA POWER** (https://power.larc.nasa.gov/) — Public Domain
- Parameter: `PRECTOTCORR` (corrected precipitation, mm/day)
- Coverage: Global, 1984-present
- No API key required

## Output Format

CSV output columns:

| Column | Description |
|--------|-------------|
| `date` | Monthly date (YYYY-MM) |
| `precipitation` | Monthly precipitation total (mm) |
| `spi` | SPI value (standardized) |
| `classification` | Drought/wet classification label |

## Batch / Multi-Location Support

```bash
# Loop over multiple locations in shell
for lat_lon in "39.9 116.4" "31.2 121.5" "23.1 113.3"; do
  set -- $lat_lon
  python scripts\drought-monitor.py spi --lat $1 --lon $2 --start 2020-01-01 --end 2023-12-31 --scale 3 --output "spi_${1}_${2}.csv"
done
```

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `ConnectionError` | Network issue | Check internet, retry |
| `HTTP 429` | Rate limit | Wait 60s, retry |
| `ValueError` | Invalid input (e.g., bad date) | Check parameter format |
| Empty output | No data for location/dates | Try different parameters |
| `ModuleNotFoundError` | Missing dep | Run pip install |

## Minimum Data Length

For reliable SPI/SPEI calculation, **at least 20–30 years of monthly data** is recommended. Shorter records may produce unreliable distribution fitting, especially for 12- and 24-month scales.

## Trend Analysis Example

```bash
# After computing SPI, run trend analysis
python scripts\drought-monitor.py report --input spi_3m.csv --output trend.json
```

The `report` subcommand performs linear regression on the SPI time series and outputs slope, p-value, and trend direction.

## Raw Data Export

To export the raw precipitation time series without SPI calculation, use:

```bash
python scripts\drought-monitor.py spi --lat 39.9042 --lon 116.4074 --start 2020-01-01 --end 2023-12-31 --scale 3 --export-raw
```

This produces an additional `raw_precipitation.csv` with daily/monthly precipitation.

## Custom Classification Thresholds

The default thresholds follow McKee et al. (1993). To customize, pass `--thresholds`:

```bash
python scripts\drought-monitor.py spi --lat 39.9042 --lon 116.4074 --start 2020-01-01 --end 2023-12-31 --scale 3 --thresholds "0.5,1.0,1.5,2.0"
```

The 4 values define boundaries between: normal / moderate / severe / extreme (symmetric for wet/dry).

## SPI Local CSV Mode

```bash
# Offline mode with pre-downloaded precipitation CSV
# CSV format: date (YYYY-MM-DD), precipitation (mm)
python scripts\drought-monitor.py spi --input precip.csv --scale 6
```

## Citation

If you use this tool, please cite the SPI methodology:

```bibtex
@article{mckee1993relationship,
  title={The relationship of drought frequency and duration to time scales},
  author={McKee, Thomas B and Doesken, Nolan J and Kleist, John and others},
  journal={Proceedings of the 8th Conference on Applied Climatology},
  volume={17},
  number={22},
  pages={179--183},
  year={1993}
}
```

## Visualization Guidance

- **Time series plot**: Plot SPI values over time with color-coded drought classification bands
- **Drought map**: Interpolate SPI values across multiple stations using IDW or Kriging for spatial drought maps
- **Trend line**: Overlay linear regression trend on SPI time series

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("spi_3m.csv")
fig, ax = plt.subplots(figsize=(12, 4))
ax.fill_between(df["date"], df["spi"], 0, where=df["spi"]<0, color="red", alpha=0.3, label="Drought")
ax.fill_between(df["date"], df["spi"], 0, where=df["spi"]>=0, color="blue", alpha=0.3, label="Wet")
ax.plot(df["date"], df["spi"], color="black", linewidth=0.8)
ax.axhline(y=0, color="gray", linestyle="--")
ax.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("spi_timeseries.png", dpi=150)
```

## Drought Classification

| SPI/SPEI Value | Classification |
|----------------|----------------|
| > 2.0 | Extremely wet |
| 1.5 to 2.0 | Very wet |
| 1.0 to 1.5 | Moderate wet |
| -1.0 to 1.0 | Normal |
| -1.5 to -1.0 | Moderate drought |
| -2.0 to -1.5 | Severe drought |
| < -2.0 | Extreme drought |

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `ConnectionError` | Network issue | Check internet, retry |
| `HTTP 429` | Rate limit | Wait 60s, retry |
| `ValueError` | Invalid input | Check parameter format |
| Empty output | No data | Try different parameters |
| `ModuleNotFoundError` | Missing dep | Run pip install |

---

## Advanced Usage

### Batch SPI for Multiple Locations
```bash
while IFS=',' read -r id lat lon; do
  python scripts\drought-monitor.py spi     --lat $lat --lon $lon --scale 3     --start 2020-01-01 --end 2023-12-31     --output spi_${id}.csv
  sleep 1
done < locations.csv
```

### CI/CD Integration (GitHub Actions)
```yaml
# .github/workflows/drought-monitor.yml
name: Drought Monitoring
on:
  schedule:
    - cron: '0 6 1 * *'  # Monthly
jobs:
  spi:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install requests scipy pandas
      - run: |
          python scripts\drought-monitor.py spi \
            --lat 39.9 --lon 116.4 --scale 3 \
            --start $(date -d '1 year ago' +%Y-%m-%d) \
            --end $(date +%Y-%m-%d) \
            --output data/beijing_spi3.csv
```

### PostgreSQL Import
```bash
python scripts\drought-monitor.py spi   --lat 39.9 --lon 116.4 --scale 3   --start 2020-01-01 --end 2023-12-31   --output spi.csv

psql -d gis_db -c "\COPY spi_index(station_id, date, spi) FROM 'spi.csv' CSV HEADER"
```

### Performance Tips
- `--scale 1` for monthly agricultural drought; `--scale 12` for long-term hydrological
- Add `sleep 1` between location queries to respect NASA POWER rate limits
- Use `--export-raw` to get precipitation data without SPI calculation

---

## 中文说明

基于 NASA POWER API 降水数据计算 SPI（标准化降水指数）和 SPEI（标准化降水蒸散指数），用于干旱监测。

## 安装

```bash
pip install requests>=2.28.0 tqdm numpy scipy pandas
# 或: pip install -r scripts/requirements.txt
```

## 依赖

| 包 | 用途 |
|-----|------|
| `scipy` | Gamma/log-logistic 分布拟合 |
| `numpy` | 数值计算 |
| `pandas` | CSV 读写和时间序列处理 |
| `requests` | NASA POWER API 调用 |
| `tqdm` | 进度条 |

## 输出格式

CSV 输出列：

| 列名 | 说明 |
|------|------|
| `date` | 月度日期（YYYY-MM） |
| `precipitation` | 月降水量（mm） |
| `spi` | SPI 值（标准化） |
| `classification` | 干旱/湿润等级标签 |

## 批量/多位置支持

```bash
# Shell 循环处理多个位置
for lat_lon in "39.9 116.4" "31.2 121.5" "23.1 113.3"; do
  set -- $lat_lon
  python scripts\drought-monitor.py spi --lat $1 --lon $2 --start 2020-01-01 --end 2023-12-31 --scale 3 --output "spi_${1}_${2}.csv"
done
```

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `ConnectionError` | 网络问题 | 检查网络，重试 |
| `HTTP 429` | 速率限制 | 等待 60 秒后重试 |
| `ValueError` | 无效输入 | 检查参数格式 |
| 空输出 | 无数据 | 尝试不同参数 |
| `ModuleNotFoundError` | 缺少依赖 | 运行 pip install |

## 最小数据长度

为获得可靠的 SPI/SPEI 计算结果，**建议使用至少 20-30 年的月数据**。较短的记录可能导致分布拟合不可靠，尤其是 12 和 24 个月尺度。

## 趋势分析示例

```bash
# 计算 SPI 后运行趋势分析
python scripts\drought-monitor.py report --input spi_3m.csv --output trend.json
```

`report` 子命令对 SPI 时间序列执行线性回归，输出斜率、p 值和趋势方向。

## 原始数据导出

导出未经 SPI 计算的原始降水时间序列：

```bash
python scripts\drought-monitor.py spi --lat 39.9042 --lon 116.4074 --start 2020-01-01 --end 2023-12-31 --scale 3 --export-raw
```

将生成包含日/月降水量的 `raw_precipitation.csv`。

## 自定义分级阈值

默认阈值遵循 McKee et al. (1993)。自定义阈值使用 `--thresholds`：

```bash
python scripts\drought-monitor.py spi --lat 39.9042 --lon 116.4074 --start 2020-01-01 --end 2023-12-31 --scale 3 --thresholds "0.5,1.0,1.5,2.0"
```

4 个值定义正常/中度/严重/极端之间的分界（湿润/干旱对称）。

## SPI 本地 CSV 模式

```bash
# 离线模式，使用预下载的降水 CSV
# CSV 格式：date (YYYY-MM-DD), precipitation (mm)
python scripts\drought-monitor.py spi --input precip.csv --scale 6
```

## 引用格式

如果使用本工具，请引用 SPI 方法论：

```bibtex
@article{mckee1993relationship,
  title={The relationship of drought frequency and duration to time scales},
  author={McKee, Thomas B and Doesken, Nolan J and Kleist, John and others},
  journal={Proceedings of the 8th Conference on Applied Climatology},
  volume={17},
  number={22},
  pages={179--183},
  year={1993}
}
```

## 可视化指南

- **时间序列图**：绘制 SPI 时间序列，按干旱等级着色
- **干旱地图**：对多个站点的 SPI 值进行 IDW 或 Kriging 插值，生成空间干旱分布图
- **趋势线**：在 SPI 时间序列上叠加线性回归趋势线

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("spi_3m.csv")
fig, ax = plt.subplots(figsize=(12, 4))
ax.fill_between(df["date"], df["spi"], 0, where=df["spi"]<0, color="red", alpha=0.3, label="干旱")
ax.fill_between(df["date"], df["spi"], 0, where=df["spi"]>=0, color="blue", alpha=0.3, label="湿润")
ax.plot(df["date"], df["spi"], color="black", linewidth=0.8)
ax.axhline(y=0, color="gray", linestyle="--")
ax.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("spi_timeseries.png", dpi=150)
```

## 故障排除

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `ConnectionError` | 网络问题 | 检查网络，重试 |
| `HTTP 429` | 速率限制 | 等待 60 秒后重试 |
| `ValueError` | 无效输入 | 检查参数格式 |
| 空输出 | 无数据 | 尝试不同参数 |
| `ModuleNotFoundError` | 缺少依赖 | 运行 pip install |

基于 NASA POWER API 降水数据计算 SPI（标准化降水指数）和 SPEI（标准化降水蒸散指数），用于干旱监测。

## 功能特性

- **SPI 计算**：伽马分布拟合 + 正态逆变换
- **SPEI 计算**：水分平衡（P - PET）+ Log-logistic 拟合
- **多时间尺度**：1、3、6、12、24 个月
- **干旱分级**：从极端干旱到极端湿润共 7 级
- **趋势分析**：SPI 时间序列线性回归
- **本地 CSV 模式**：支持离线处理已有数据
- **NASA POWER 集成**：自动获取全球降水数据（无需 API key）

## 使用方法

```bash
# 计算北京 3 个月 SPI
python scripts\drought-monitor.py spi --lat 39.9042 --lon 116.4074 --start 2020-01-01 --end 2023-12-31 --scale 3

# 从本地 CSV 计算 12 个月 SPEI
python scripts\drought-monitor.py spei --input water_balance.csv --scale 12

# 生成干旱报告
python scripts\drought-monitor.py report --input spi_3m.csv --output report.json
```

## 数据来源

- **NASA POWER** (https://power.larc.nasa.gov/) — 公共领域
- 参数：`PRECTOTCORR`（校正降水量，mm/天）
- 覆盖范围：全球，1984 年至今
- 无需 API key

## 干旱分级标准

| SPI/SPEI 值 | 等级 |
|-------------|------|
| > 2.0 | 极端湿润 |
| 1.5 至 2.0 | 非常湿润 |
| 1.0 至 1.5 | 中度湿润 |
| -1.0 至 1.0 | 正常 |
| -1.5 至 -1.0 | 中度干旱 |
| -2.0 至 -1.5 | 严重干旱 |
| < -2.0 | 极端干旱 |
