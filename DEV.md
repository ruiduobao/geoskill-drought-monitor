# drought-monitor - Development Doc

## Purpose
Calculate SPI (Standardized Precipitation Index) and SPEI (Standardized Precipitation Evapotranspiration Index)
from NASA POWER API precipitation data for drought monitoring.

## Data Source
- NASA POWER API: `https://power.larc.nasa.gov/api/temporal/daily/point`
- Parameters: `PRECTOTCORR` (precipitation mm/day)
- No API key required
- Coverage: global, 1984-present

## SPI Calculation Method
1. Accumulate precipitation over target timescale (1, 3, 6, 12 months)
2. Fit gamma distribution to accumulated precipitation (MLE)
3. Transform CDF to standard normal distribution (inverse normal)
4. Classify per SPI value

## SPEI Calculation Method
1. Compute climatic water balance: D = P - PET
2. Accumulate D over target timescale
3. Fit log-logistic distribution (or gamma)
4. Transform to standard normal

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

## CLI Design
```
drought-monitor spi --lat --lon --start --end --scale --output
drought-monitor spei --lat --lon --start --end --scale --output
drought-monitor report --input --output
```

## Dependencies
- requests>=2.28.0
- numpy>=1.21.0
- scipy>=1.7.0
- tqdm>=4.60.0

## Implementation Notes
- Gamma fitting via scipy.stats.gamma.fit (MLE)
- Handle zero precipitation (common in arid regions) with modified gamma
- Inverse normal via scipy.stats.norm.ppf
- NASA POWER API: request daily data, then accumulate locally
- Support local CSV input (columns: date, precipitation) for offline mode
