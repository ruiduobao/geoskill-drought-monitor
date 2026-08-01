#!/usr/bin/env python3
"""
drought-monitor: SPI/SPEI Drought Index Calculator
===================================================
Calculate Standardized Precipitation Index (SPI) and
Standardized Precipitation Evapotranspiration Index (SPEI)
from NASA POWER API data or local CSV.

Privacy Disclosure:
- When using NASA POWER API: latitude, longitude, date range, and
  parameter selection are sent to power.larc.nasa.gov via HTTPS.
- No API key, personal identifiers, or IP logging by NASA.
- Local CSV mode: all processing is offline, no data leaves your machine.

Data Source:
- NASA POWER Project (https://power.larc.nasa.gov/) — Public Domain
- CHIRPS (https://www.chc.ucsb.edu/data/chirps) — Public Domain

License: MIT-0 (No attribution required)
Author: ruiduobao
Version: 0.1.0
"""

import argparse
import sys
import os
import json
import csv
import time
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is required. Install with: pip install requests>=2.28.0")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("ERROR: 'numpy' is required. Install with: pip install numpy>=1.21.0")
    sys.exit(1)

try:
    from scipy import stats as scipy_stats
except ImportError:
    print("ERROR: 'scipy' is required. Install with: pip install scipy>=1.7.0")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):
        return iterable


# ============================================================
# Place resolver (v0.2.0 — batch2 upgrade)
# ============================================================

def _resolve_place(place: str):
    """Resolve a Chinese place name to (lat, lon, bbox).

    Returns a place_resolver.PlaceInfo or raises ValueError.
    """
    import os
    import sys

    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "_shared"),
        os.path.join(os.getcwd(), "_shared"),
    ]
    for c in candidates:
        full = os.path.abspath(c)
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, "place_resolver.py")):
            if full not in sys.path:
                sys.path.insert(0, full)
            try:
                import place_resolver  # type: ignore
                return place_resolver.resolve_place(place)
            except Exception:
                continue
    raise ValueError(f"无法解析地点 '{place}' (place_resolver unavailable)")


# ============================================================
# Constants
# ============================================================

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

DROUGHT_CLASSES = [
    (2.0, float("inf"), "Extremely wet"),
    (1.5, 2.0, "Very wet"),
    (1.0, 1.5, "Moderate wet"),
    (-1.0, 1.0, "Normal"),
    (-1.5, -1.0, "Moderate drought"),
    (-2.0, -1.5, "Severe drought"),
    (float("-inf"), -2.0, "Extreme drought"),
]

VALID_SCALES = [1, 3, 6, 12, 24]
VALID_PARAMETERS = ["PRECTOTCORR", "PRECTOT"]

# Presets for common drought-monitor use cases (v0.2.0)
PRESETS = {
    "drought-china": {
        "description": "中国典型干旱监测：3 个月 SPI（农业干旱）",
        "scale": 3,
        "parameter": "PRECTOTCORR",
        "start_default": "1990-01-01",
        "end_default": "2024-12-31",
    },
    "drought-china-12m": {
        "description": "中国典型干旱监测：12 个月 SPI（水文干旱）",
        "scale": 12,
        "parameter": "PRECTOTCORR",
        "start_default": "1990-01-01",
        "end_default": "2024-12-31",
    },
    "drought-china-spei": {
        "description": "中国典型干旱监测：3 个月 SPEI（来自本地 P-PET CSV）",
        "scale": 3,
        "parameter": "PRECTOTCORR",
        "start_default": "1990-01-01",
        "end_default": "2024-12-31",
    },
}


# ============================================================
# NASA POWER API
# ============================================================

def fetch_nasa_power(
    lat: float,
    lon: float,
    start: str,
    end: str,
    parameter: str = "PRECTOTCORR",
    timeout: int = 120,
) -> List[Dict]:
    """Fetch daily precipitation from NASA POWER API.

    Args:
        lat: Latitude (-90 to 90)
        lon: Longitude (-180 to 180)
        start: Start date (YYYYMMDD)
        end: End date (YYYYMMDD)
        parameter: NASA POWER parameter name
        timeout: Request timeout in seconds

    Returns:
        List of dicts with 'date' (str) and 'value' (float)
    """
    params = {
        "parameters": parameter,
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start,
        "end": end,
        "format": "JSON",
    }

    print(f"Fetching NASA POWER data: lat={lat}, lon={lon}, {start} to {end}")
    print(f"  Parameter: {parameter}")
    print(f"  URL: {NASA_POWER_URL}")

    try:
        resp = requests.get(NASA_POWER_URL, params=params, timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        print("ERROR: Request timed out. Try a shorter date range or check your connection.")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("ERROR: Connection failed. Check your internet connection.")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP {resp.status_code}: {e}")
        if resp.status_code == 422:
            print("  Hint: Check that coordinates are within valid range and dates are correct.")
        sys.exit(1)

    data = resp.json()

    if "properties" not in data or "parameter" not in data["properties"]:
        print("ERROR: Unexpected API response format.")
        print(f"  Response keys: {list(data.keys())}")
        sys.exit(1)

    param_data = data["properties"]["parameter"].get(parameter, {})
    if not param_data:
        print(f"ERROR: No data returned for parameter '{parameter}'.")
        sys.exit(1)

    results = []
    for date_str, value in sorted(param_data.items()):
        # NASA POWER uses -999 for missing values
        if value == -999 or value == -9999:
            continue
        results.append({"date": date_str, "value": float(value)})

    print(f"  Retrieved {len(results)} daily records.")
    return results


# ============================================================
# SPI Calculation
# ============================================================

def accumulate_precip(data: List[Dict], scale: int) -> List[Dict]:
    """Accumulate precipitation over rolling window.

    Args:
        data: List of daily records {'date': 'YYYYMMDD', 'value': float}
        scale: Accumulation period in months (approx 30-day months)

    Returns:
        List of monthly accumulated values
    """
    # Convert to monthly totals first
    monthly = {}
    for rec in data:
        ym = rec["date"][:6]  # YYYYMM
        monthly[ym] = monthly.get(ym, 0.0) + max(0, rec["value"])

    months_sorted = sorted(monthly.keys())
    window = scale

    accumulated = []
    for i in range(window - 1, len(months_sorted)):
        window_months = months_sorted[i - window + 1 : i + 1]
        total = sum(monthly[m] for m in window_months)
        accumulated.append({"date": months_sorted[i], "value": total})

    return accumulated


def fit_gamma(data: np.ndarray) -> Tuple[float, float, float]:
    """Fit gamma distribution to precipitation data using MLE.

    Returns:
        (shape, loc, scale) parameters
    """
    # Remove zeros for gamma fitting (use mixed distribution approach)
    positive = data[data > 0]
    if len(positive) < 3:
        return None

    # Probability of zero
    p_zero = 1.0 - len(positive) / len(data)

    # Fit gamma to positive values
    shape, loc, scale = scipy_stats.gamma.fit(positive, floc=0)

    return shape, loc, scale, p_zero


def compute_spi(accumulated: List[Dict], scale: int) -> List[Dict]:
    """Compute SPI from accumulated precipitation.

    Args:
        accumulated: List of {'date': 'YYYYMM', 'value': float}
        scale: Timescale in months

    Returns:
        List of {'date': str, 'spi': float, 'classification': str}
    """
    values = np.array([r["value"] for r in accumulated])

    if len(values) < 10:
        print(f"WARNING: Only {len(values)} data points. SPI may be unreliable.")

    # Fit gamma distribution
    positive = values[values > 0]
    if len(positive) < 3:
        print("ERROR: Insufficient positive precipitation values for gamma fitting.")
        return []

    p_zero = 1.0 - len(positive) / len(values)
    shape, loc, scale_param = scipy_stats.gamma.fit(positive, floc=0)

    results = []
    for i, rec in enumerate(accumulated):
        x = rec["value"]
        if x <= 0:
            spi = -3.0  # Assign extreme drought for zero precip
        else:
            # Gamma CDF
            cdf = scipy_stats.gamma.cdf(x, shape, loc=loc, scale=scale_param)
            # Adjust for zero probability
            cdf_adjusted = p_zero + (1 - p_zero) * cdf
            # Clamp to avoid infinities
            cdf_adjusted = np.clip(cdf_adjusted, 0.001, 0.999)
            # Inverse normal
            spi = scipy_stats.norm.ppf(cdf_adjusted)

        classification = classify_spi(spi)
        results.append({
            "date": rec["date"],
            "precipitation": round(rec["value"], 2),
            "spi": round(spi, 4),
            "classification": classification,
        })

    return results


def classify_spi(spi: float) -> str:
    """Classify SPI value into drought category."""
    for low, high, label in DROUGHT_CLASSES:
        if low <= spi < high:
            return label
    return "Unknown"


# ============================================================
# SPEI Calculation (simplified)
# ============================================================

def compute_spei_from_csv(data: List[Dict], scale: int) -> List[Dict]:
    """Compute SPEI from pre-computed water balance data (P - PET).

    Args:
        data: List of {'date': 'YYYYMM', 'value': float} (monthly water balance)
        scale: Timescale in months

    Returns:
        List of {'date': str, 'spei': float, 'classification': str}
    """
    values = np.array([r["value"] for r in data])

    if len(values) < 10:
        print(f"WARNING: Only {len(values)} data points. SPEI may be unreliable.")

    # Accumulate over scale
    accumulated = []
    for i in range(scale - 1, len(values)):
        window = values[i - scale + 1 : i + 1]
        accumulated.append(float(np.sum(window)))

    if len(accumulated) < 5:
        print("ERROR: Insufficient data for SPEI calculation.")
        return []

    # Fit log-logistic distribution (using GEV as approximation)
    # For simplicity, use normal fit on accumulated values
    mu = np.mean(accumulated)
    sigma = np.std(accumulated)

    if sigma == 0:
        print("ERROR: Zero variance in data.")
        return []

    results = []
    for i, acc_val in enumerate(accumulated):
        # Standardize
        z = (acc_val - mu) / sigma
        classification = classify_spi(z)  # Same classification scheme
        results.append({
            "date": data[i + scale - 1]["date"],
            "water_balance": round(acc_val, 2),
            "spei": round(z, 4),
            "classification": classification,
        })

    return results


# ============================================================
# Report Generation
# ============================================================

def generate_report(spi_results: List[Dict], output_path: str) -> Dict:
    """Generate drought summary report."""
    if not spi_results:
        print("ERROR: No results to report.")
        return {}

    spi_values = [r["spi"] for r in spi_results]
    classifications = [r["classification"] for r in spi_results]

    # Count by class
    class_counts = {}
    for c in classifications:
        class_counts[c] = class_counts.get(c, 0) + 1

    # Drought frequency (moderate + severe + extreme)
    drought_classes = {"Moderate drought", "Severe drought", "Extreme drought"}
    drought_count = sum(1 for c in classifications if c in drought_classes)
    drought_freq = drought_count / len(classifications) * 100

    # Trend: simple linear regression on SPI
    x = np.arange(len(spi_values))
    slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, spi_values)

    report = {
        "period": {
            "start": spi_results[0]["date"],
            "end": spi_results[-1]["date"],
            "total_months": len(spi_results),
        },
        "spi_statistics": {
            "mean": round(float(np.mean(spi_values)), 4),
            "std": round(float(np.std(spi_values)), 4),
            "min": round(float(np.min(spi_values)), 4),
            "max": round(float(np.max(spi_values)), 4),
        },
        "classification_counts": class_counts,
        "drought_frequency_percent": round(drought_freq, 2),
        "trend": {
            "slope_per_month": round(float(slope), 6),
            "r_squared": round(float(r_value ** 2), 4),
            "p_value": round(float(p_value), 6),
            "direction": "wetter" if slope > 0.001 else ("drier" if slope < -0.001 else "stable"),
        },
    }

    # Write report
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nReport saved to: {output_path}")
    print(f"  Period: {report['period']['start']} to {report['period']['end']}")
    print(f"  Mean SPI: {report['spi_statistics']['mean']}")
    print(f"  Drought frequency: {report['drought_frequency_percent']}%")
    print(f"  Trend: {report['trend']['direction']} (slope={report['trend']['slope_per_month']})")

    return report


# ============================================================
# Output
# ============================================================

def write_csv(results: List[Dict], output_path: str):
    """Write results to CSV."""
    if not results:
        print("WARNING: No results to write.")
        return

    fieldnames = results[0].keys()
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Results saved to: {output_path} ({len(results)} records)")


def write_json(results: List[Dict], output_path: str):
    """Write results to JSON (pretty-printed array)."""
    if not results:
        print("WARNING: No results to write.")
        return
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"Results saved to: {output_path} ({len(results)} records)")


def write_ndjson(results: List[Dict], output_path: str):
    """Write results to NDJSON (one JSON object per line)."""
    if not results:
        print("WARNING: No results to write.")
        return
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    print(f"Results saved to: {output_path} ({len(results)} records)")


def write_results(results: List[Dict], output_path: str, fmt: str = "csv"):
    """Dispatch writer based on --format.

    Supported: csv, json, ndjson.
    Default: csv (backwards-compatible).
    """
    fmt = (fmt or "csv").lower()
    if fmt == "csv":
        write_csv(results, output_path)
    elif fmt == "json":
        write_json(results, output_path)
    elif fmt == "ndjson":
        write_ndjson(results, output_path)
    else:
        print(f"WARNING: Unknown --format '{fmt}', falling back to csv")
        write_csv(results, output_path)


# ============================================================
# CLI Subcommands
# ============================================================

def cmd_spi(args):
    """Calculate SPI from NASA POWER data or local CSV."""
    # --preset (v0.2.0)
    if getattr(args, "preset", None):
        ps = PRESETS[args.preset]
        print(f"[preset] {args.preset}: {ps['description']}")
        if not args.start:
            args.start = ps["start_default"]
        if not args.end:
            args.end = ps["end_default"]
        if args.scale == 3 and ps["scale"] != 3:
            args.scale = ps["scale"]

    # --place resolves to lat/lon when lat/lon are missing
    if not args.input and args.place and (args.lat is None or args.lon is None):
        try:
            pi = _resolve_place(args.place)
            args.lat = pi.centroid[1]
            args.lon = pi.centroid[0]
            print(f"[place] {args.place} -> {pi.resolved_name} (lat={args.lat:.4f}, lon={args.lon:.4f})")
            print(f"[place] source={pi.source} code={pi.code} confidence={pi.confidence}")
            if not args.start:
                args.start = "1990-01-01"
            if not args.end:
                args.end = "2024-12-31"
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    if args.input:
        # Local CSV mode
        print(f"Reading local CSV: {args.input}")
        data = []
        with open(args.input, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append({"date": row["date"], "value": float(row["precipitation"])})
        print(f"  Loaded {len(data)} records.")
    else:
        # Validate coordinates
        if not (-90 <= args.lat <= 90):
            print(f"ERROR: Latitude {args.lat} out of range [-90, 90].")
            sys.exit(1)
        if not (-180 <= args.lon <= 180):
            print(f"ERROR: Longitude {args.lon} out of range [-180, 180].")
            sys.exit(1)

        # Fetch from NASA POWER
        start_str = args.start.replace("-", "")
        end_str = args.end.replace("-", "")
        data = fetch_nasa_power(args.lat, args.lon, start_str, end_str)

    if not data:
        print("ERROR: No data available.")
        sys.exit(1)

    # Accumulate
    accumulated = accumulate_precip(data, args.scale)
    print(f"  {args.scale}-month accumulated: {len(accumulated)} values.")

    # Compute SPI
    results = compute_spi(accumulated, args.scale)

    if not results:
        print("ERROR: SPI computation failed.")
        sys.exit(1)

    # Output
    fmt = getattr(args, "format", "csv")
    default_ext = ".json" if fmt == "json" else (".ndjson" if fmt == "ndjson" else ".csv")
    if args.output:
        output_path = args.output
    else:
        output_path = f"spi_{args.scale}m{default_ext}"
    write_results(results, output_path, fmt=fmt)

    # Print summary
    drought_months = sum(1 for r in results if "drought" in r["classification"].lower())
    print(f"\nSummary: {drought_months}/{len(results)} months in drought.")

    # QA summary (v0.2.0)
    if getattr(args, "qa", False):
        qa_path = os.path.splitext(output_path)[0] + ".qa.json"
        classifications = [r["classification"] for r in results]
        class_counts = {}
        for c in classifications:
            class_counts[c] = class_counts.get(c, 0) + 1
        qa = {
            "place": getattr(args, "place", None),
            "resolved_centroid": [args.lon, args.lat] if args.lat is not None else None,
            "scale_months": args.scale,
            "start": args.start,
            "end": args.end,
            "n_records": len(results),
            "drought_months": drought_months,
            "drought_frequency_percent": round(drought_months / max(1, len(results)) * 100, 2),
            "classification_counts": class_counts,
            "preset": getattr(args, "preset", None),
            "output_csv": output_path,
        }
        with open(qa_path, "w", encoding="utf-8") as f:
            json.dump(qa, f, indent=2, ensure_ascii=False)
        print(f"  QA summary: {qa_path}")


def cmd_spei(args):
    """Calculate SPEI from local water balance CSV."""
    if not args.input:
        print("ERROR: SPEI requires local CSV input with water balance data.")
        print("  CSV must have columns: 'date' (YYYYMM), 'precipitation', 'pet'")
        print("  Or pre-computed: 'date', 'water_balance'")
        sys.exit(1)

    print(f"Reading local CSV: {args.input}")
    data = []
    with open(args.input, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "water_balance" in row:
                data.append({"date": row["date"], "value": float(row["water_balance"])})
            else:
                p = float(row["precipitation"])
                pet = float(row["pet"])
                data.append({"date": row["date"], "value": p - pet})

    print(f"  Loaded {len(data)} records.")

    results = compute_spei_from_csv(data, args.scale)

    if not results:
        print("ERROR: SPEI computation failed.")
        sys.exit(1)

    output_path = args.output or f"spei_{args.scale}m.csv"
    fmt = getattr(args, "format", "csv")
    write_results(results, output_path, fmt=fmt)


def cmd_report(args):
    """Generate drought report from SPI/SPEI CSV."""
    print(f"Reading results: {args.input}")
    results = []
    with open(args.input, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "spi" in row:
                row["spi"] = float(row["spi"])
            if "spei" in row:
                row["spei"] = float(row["spei"])
            results.append(row)

    print(f"  Loaded {len(results)} records.")

    output_path = args.output or "drought_report.json"
    generate_report(results, output_path)


# ============================================================
# Main CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        prog="drought-monitor",
        description="SPI/SPEI Drought Index Calculator — Monitor drought using NASA POWER data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Calculate 3-month SPI for Beijing
  python drought-monitor.py spi --lat 39.9042 --lon 116.4074 --start 2020-01-01 --end 2023-12-31 --scale 3

  # Calculate 12-month SPEI from local water balance CSV
  python drought-monitor.py spei --input water_balance.csv --scale 12

  # Generate drought report
  python drought-monitor.py report --input spi_3m.csv --output report.json

Drought Classification:
  SPI > 2.0    : Extremely wet
  1.5 to 2.0   : Very wet
  1.0 to 1.5   : Moderate wet
  -1.0 to 1.0  : Normal
  -1.5 to -1.0 : Moderate drought
  -2.0 to -1.5 : Severe drought
  < -2.0       : Extreme drought
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Subcommand")

    # --- spi ---
    spi_parser = subparsers.add_parser("spi", help="Calculate SPI from NASA POWER or local CSV")
    spi_parser.add_argument("--lat", type=float, help="Latitude (-90 to 90)")
    spi_parser.add_argument("--lon", type=float, help="Longitude (-180 to 180)")
    spi_parser.add_argument("--place", type=str, help="Place name (Chinese or English); auto-resolved to lat/lon")
    spi_parser.add_argument("--preset", choices=list(PRESETS.keys()),
                            help="Use a preset configuration (drought-china, drought-china-12m, ...)")
    spi_parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    spi_parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    spi_parser.add_argument("--scale", type=int, default=3, choices=VALID_SCALES,
                            help="SPI timescale in months (default: 3)")
    spi_parser.add_argument("--input", type=str, help="Local CSV (date, precipitation) for offline mode")
    spi_parser.add_argument("--output", type=str, help="Output CSV path")
    spi_parser.add_argument("--format", choices=["csv", "json", "ndjson"], default="csv",
                             help="Output format (default: csv)")
    spi_parser.add_argument("--qa", action="store_true", help="Write a QA summary JSON next to the output")
    spi_parser.set_defaults(func=cmd_spi)

    # --- spei ---
    spei_parser = subparsers.add_parser("spei", help="Calculate SPEI from local water balance CSV")
    spei_parser.add_argument("--input", type=str, required=True,
                             help="Local CSV with water balance data")
    spei_parser.add_argument("--scale", type=int, default=3, choices=VALID_SCALES,
                             help="SPEI timescale in months (default: 3)")
    spei_parser.add_argument("--output", type=str, help="Output CSV path")
    spei_parser.add_argument("--format", choices=["csv", "json", "ndjson"], default="csv",
                             help="Output format (default: csv)")
    spei_parser.set_defaults(func=cmd_spei)

    # --- report ---
    report_parser = subparsers.add_parser("report", help="Generate drought summary report")
    report_parser.add_argument("--input", type=str, required=True, help="SPI/SPEI CSV file")
    report_parser.add_argument("--output", type=str, help="Output JSON path")
    report_parser.set_defaults(func=cmd_report)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    return args.func(args)
if __name__ == "__main__":
    sys.exit(main())
