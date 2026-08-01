# drought-monitor

**SPI/SPEI Drought Index Calculator** — Monitor drought using NASA POWER precipitation data.

## Install

### ClawHub
```bash
clawhub install drought-monitor
```

### Manual
```bash
git clone https://github.com/ruiduobao/drought-monitor.git
cd drought-monitor
pip install -r requirements.txt  # requests, numpy, scipy, tqdm
```

### Claude Code / skills.sh
```bash
/clawhub install drought-monitor
```

## Quick Start
```bash
python scripts/drought-monitor.py spi --lat 39.9042 --lon 116.4074 --start 2020-01-01 --end 2023-12-31 --scale 3
python scripts/drought-monitor.py report --input spi_3m.csv
```

## Data Source
- NASA POWER (https://power.larc.nasa.gov/) — Public Domain

## License
MIT-0

---

# 干旱监测工具

**SPI/SPEI 干旱指数计算器** — 基于 NASA POWER 降水数据的干旱监测。

## 安装

### 手动安装
```bash
git clone https://github.com/ruiduobao/drought-monitor.git
cd drought-monitor
pip install requests numpy scipy tqdm
```

## 快速开始
```bash
python scripts/drought-monitor.py spi --lat 39.9042 --lon 116.4074 --start 2020-01-01 --end 2023-12-31 --scale 3
python scripts/drought-monitor.py report --input spi_3m.csv
```

## 数据来源
- NASA POWER (https://power.larc.nasa.gov/) — 公共领域

## 许可证
MIT-0
