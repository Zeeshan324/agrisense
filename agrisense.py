"""AgriSense data adapters and suitability calculations."""
import calendar
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

DATA = Path(__file__).parent / "data"
FIRST_YEAR, LAST_YEAR = 1991, 2020
POWER = "https://power.larc.nasa.gov/api/temporal/monthly/point"
SOILS = {
    1: ("Sand", "light"), 2: ("Loamy sand", "light"),
    3: ("Sandy loam", "medium"), 4: ("Silt loam", "medium"),
    5: ("Silt", "medium"), 6: ("Loam", "medium"),
    7: ("Sandy clay loam", "medium"), 8: ("Silty clay loam", "medium"),
    9: ("Clay loam", "medium"), 10: ("Sandy clay", "heavy"),
    11: ("Silty clay", "heavy"), 12: ("Clay", "heavy"),
    13: ("Organic materials", "organic"), 14: ("Water", None),
    15: ("Bedrock", None), 16: ("Other", None),
}


@dataclass(frozen=True)
class Crop:
    name: str
    common: str
    temperature: tuple
    rainfall: tuple
    optimal_soil: frozenset
    tolerated_soil: frozenset
    soil_preferences: dict[str, str]
    is_tree: bool
    fruit_or_nut: bool


def load_grid():
    from netCDF4 import Dataset

    with Dataset(DATA / "GLDASp5_soiltexture_025d.nc4") as dataset:
        return tuple(dataset[name][:] for name in ("lat", "lon", "GLDAS_soiltex"))


def soil_at(grid, latitude, longitude):
    import numpy as np

    lat, lon, values = grid
    row = abs(lat - latitude).argmin()
    column = abs(lon - longitude).argmin()
    raw = values[0, row, column]
    if np.ma.is_masked(raw) or not math.isfinite(raw):
        return "No soil data", None
    code = round(float(raw))
    if abs(raw - code) > 0.0001:
        return "Unrecognized soil class", None
    return SOILS.get(code, ("No soil data", None))


def thresholds(row, keys):
    values = tuple(float(row[key]) for key in keys)
    if not all(map(math.isfinite, values)) or tuple(sorted(values)) != values:
        raise ValueError("Invalid thresholds")
    return values


def texture_labels(value):
    return frozenset(label.strip().lower() for label in value.split(",")) & {
        "light", "medium", "heavy", "organic", "wide"
    }


def load_crops():
    crops = []
    with (DATA / "EcoCrop_DB.csv").open(encoding="cp1252", newline="") as source:
        for row in csv.DictReader(source):
            try:
                temperature = thresholds(row, ("TMIN", "TOPMN", "TOPMX", "TMAX"))
                rainfall = thresholds(row, ("RMIN", "ROPMN", "ROPMX", "RMAX"))
            except ValueError:
                continue
            soil_preferences = {}
            try:
                ph_low, ph_high = thresholds(row, ("PHOPMN", "PHOPMX"))
                if 0 < ph_low <= ph_high <= 14:
                    soil_preferences["Soil pH"] = f"{ph_low:g} to {ph_high:g}"
            except ValueError:
                pass
            for field, label in (("DRA", "Drainage"), ("DEP", "Soil depth"),
                                 ("SAL", "Soil salinity"), ("FER", "Soil fertility")):
                value = row[field].strip()
                if value.upper() not in {"", "NA"}:
                    soil_preferences[label] = value.removesuffix(")") if value.endswith("))") else value
            name = row["ScientificName"]
            common = "Maize (corn)" if name == "Zea mays ssp. mays" else row["COMNAME"].split(",")[0]
            life_forms = {value.strip() for value in row["LIFO"].split(",")}
            categories = {value.strip() for value in row["CAT"].split(",")}
            crops.append(Crop(name, common,
                              temperature, rainfall, texture_labels(row["TEXT"]),
                              texture_labels(row["TEXTR"]), soil_preferences,
                              "tree" in life_forms, "fruits & nuts" in categories))
    return crops


def fetch_climate(latitude, longitude):
    query = urlencode(dict(parameters="T2M,PRECTOTCORR", community="AG",
                           latitude=latitude, longitude=longitude, format="JSON",
                           start=FIRST_YEAR, end=LAST_YEAR))
    with urlopen(f"{POWER}?{query}", timeout=25) as response:
        return summarize_climate(json.load(response))


def summarize_climate(payload):
    parameters = payload["properties"]["parameter"]
    units = payload["parameters"]
    if units["T2M"]["units"].upper() != "C":
        raise ValueError("Unexpected NASA POWER temperature units.")
    rain_units = units["PRECTOTCORR"]["units"].lower().replace(" ", "")
    if rain_units not in {"mm/day", "mm/month", "mm"}:
        raise ValueError("Unexpected NASA POWER precipitation units.")
    fill = payload["header"]["fill_value"]
    monthly_temperature = [[] for _ in range(12)]
    monthly_rainfall = [[] for _ in range(12)]
    annual_rainfall = []
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        yearly_rainfall = 0
        for month in range(1, 13):
            key = f"{year}{month:02}"
            temperature = parameters["T2M"].get(key, fill)
            rain = parameters["PRECTOTCORR"].get(key, fill)
            if (temperature == fill or rain == fill or not math.isfinite(temperature)
                    or not math.isfinite(rain) or rain < 0):
                raise ValueError(f"Missing or invalid NASA POWER data for {year}-{month:02}.")
            days = calendar.monthrange(year, month)[1]
            monthly_temperature[month - 1].append(temperature)
            monthly_total = rain * days if rain_units == "mm/day" else rain
            monthly_rainfall[month - 1].append(monthly_total)
            yearly_rainfall += monthly_total
        annual_rainfall.append(yearly_rainfall)
    return ([sum(values) / len(values) for values in monthly_temperature],
            sum(annual_rainfall) / len(annual_rainfall),
            [sum(values) / len(values) for values in monthly_rainfall])


def suitability(value, limits):
    minimum, optimal_low, optimal_high, maximum = limits
    if value < minimum or value > maximum:
        return 0.0
    if value < optimal_low:
        return (value - minimum) / (optimal_low - minimum)
    if value > optimal_high:
        return (maximum - value) / (maximum - optimal_high)
    return 1.0


def soil_match(crop, group):
    if not group:
        return "No location soil data"
    if group in crop.optimal_soil:
        return "Preferred"
    if group in crop.tolerated_soil:
        return "Tolerated"
    if "wide" in crop.optimal_soil | crop.tolerated_soil:
        return "Broad tolerance"
    if crop.tolerated_soil:
        return "Outside stated range"
    return "Crop tolerance unspecified"


def rank(crops, climate, soil_group, start_month, months, *, irrigate=False):
    temperatures, rainfall, _ = climate
    season = [temperatures[(start_month - 1 + offset) % 12] for offset in range(months)]
    mean_temperature = sum(season) / len(season)
    results = []
    for crop in crops:
        temperature_fit = suitability(mean_temperature, crop.temperature)
        rainfall_fit = suitability(rainfall, crop.rainfall)
        texture = soil_match(crop, soil_group)
        score = 100 * temperature_fit * (1 if irrigate else rainfall_fit)
        if texture == "Outside stated range":
            score = 0.0
        results.append({
            "Crop": crop.name,
            "Common name": crop.common,
            "Score": 100.0 if score == 100 else min(99.9, round(score, 1) or score),
            "Temperature fit": round(100 * temperature_fit),
            "Rainfall fit": round(100 * rainfall_fit),
            "Soil texture": texture,
        })
    priority = {"Preferred": 0, "Tolerated": 1, "Broad tolerance": 2}
    results.sort(key=lambda row: (-row["Score"], priority.get(row["Soil texture"], 3), row["Crop"]))
    return mean_temperature, results


def limit_matches(results):
    """Keep positive matches and expand lists with many perfect scores."""
    limit = 50 if sum(row["Score"] == 100 for row in results) > 25 else 25
    return [row for row in results if row["Score"] > 0][:limit], limit
