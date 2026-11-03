"""Poisson / negative-binomial demand models and the dashboard payload.

The mean of an NB2 model does not depend on its dispersion parameter, so the
Poisson MLE is also the NB mean fit.  We estimate alpha separately by profile
likelihood, then use it for honest predictive intervals.
"""

import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy.optimize import minimize_scalar
from scipy.stats import nbinom, poisson
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from app.data import load_data

COUNT_FORMULA = (
    "count ~ C(hour) * weekend + C(season) + holiday_flag "
    "+ temp + I(temp**2) + humidity + wind + visibility "
    "+ log_solar + log_rain + snow"
)
CALENDAR_FORMULA = "count ~ C(hour) * weekend + C(season) + holiday_flag"
WEATHER_FORMULA = (
    "count ~ temp + I(temp**2) + humidity + wind + visibility "
    "+ log_solar + log_rain + snow"
)

SEASONS = ("Spring", "Summer", "Autumn", "Winter")
COMMUTE_HOURS = (7, 8, 9, 17, 18, 19)
TEST_DAYS = 14


@dataclass
class Bundle:
    data: pd.DataFrame
    train: pd.DataFrame
    test: pd.DataFrame
    mean_model: Any
    ets: Any
    alpha: float
    overdispersed: bool
    metrics: list[dict]
    season_stats: dict
    payload: dict = field(default_factory=dict)


def _scores(actual: np.ndarray, predicted: np.ndarray) -> dict:
    error = np.asarray(actual, dtype=float) - np.asarray(predicted, dtype=float)
    return {
        "mae": round(float(np.mean(np.abs(error))), 2),
        "rmse": round(float(np.sqrt(np.mean(error**2))), 2),
    }


def _nb_alpha(y: np.ndarray, mu: np.ndarray) -> tuple[float, float]:
    """Profile-likelihood estimate of the NB2 dispersion and its log-likelihood."""

    def negative_log_likelihood(alpha: float) -> float:
        size = 1.0 / alpha
        prob = size / (size + mu)
        return -float(nbinom.logpmf(y, size, prob).sum())

    result = minimize_scalar(
        negative_log_likelihood,
        bounds=(1e-4, 10.0),
        method="bounded",
        options={"xatol": 1e-6},
    )
    alpha = float(result.x)
    return alpha, -float(result.fun)


def _hour_profile(frame: pd.DataFrame) -> list[float]:
    values = frame.groupby("hour")["count"].mean().reindex(range(24), fill_value=0.0)
    return [round(float(v), 1) for v in values]


def _matrix(frame: pd.DataFrame, column: str, values: list[int]) -> list[list[int]]:
    table = frame.pivot_table(
        index=column, columns="hour", values="count", aggfunc="mean"
    ).reindex(values)
    table = table.reindex(columns=range(24), fill_value=0.0)
    return [[int(round(float(v))) for v in row] for row in table.fillna(0).to_numpy()]


def build_bundle(data: pd.DataFrame | None = None) -> Bundle:
    data = load_data() if data is None else data
    operating = data[data["operating"]].copy()

    test_start = operating["date"].max() - pd.Timedelta(days=TEST_DAYS - 1)
    train = operating[operating["timestamp"] < test_start].copy()
    test = operating[operating["timestamp"] >= test_start].copy()

    mean_model = smf.glm(COUNT_FORMULA, data=train, family=sm.families.Poisson()).fit()
    calendar_model = smf.glm(
        CALENDAR_FORMULA, data=train, family=sm.families.Poisson()
    ).fit()
    weather_model = smf.glm(
        WEATHER_FORMULA, data=train, family=sm.families.Poisson()
    ).fit()

    predicted = mean_model.predict(test).to_numpy(dtype=float)
    actual = test["count"].to_numpy(dtype=float)

    alpha, nb_log_likelihood = _nb_alpha(
        train["count"].to_numpy(), mean_model.fittedvalues.to_numpy()
    )
    n_params = len(mean_model.params)
    nb_aic = 2 * (n_params + 1) - 2 * nb_log_likelihood

    # Continuous clock for the time-series baseline. Closed hours are zeros.
    full_series = (
        data.set_index("timestamp")["count"]
        .sort_index()
        .asfreq("h")
        .astype(float)
        .fillna(0.0)
    )
    train_series = full_series[full_series.index < test_start]
    horizon = int((full_series.index.max() - test_start) / pd.Timedelta(hours=1)) + 1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ets = ExponentialSmoothing(
            train_series,
            trend=None,
            seasonal="add",
            seasonal_periods=24,
            initialization_method="estimated",
        ).fit()
    ets_test = (
        ets.forecast(horizon).reindex(pd.DatetimeIndex(test["timestamp"])).to_numpy()
    )

    poisson_scores = _scores(actual, predicted)
    nb_scores = dict(poisson_scores)  # NB2 uses the same conditional mean
    ets_scores = _scores(actual, ets_test)

    metrics = [
        {
            "key": "poisson",
            "name": "Poisson GLM",
            "family": "count regression",
            "mae": poisson_scores["mae"],
            "rmse": poisson_scores["rmse"],
            "aic": int(round(mean_model.aic)),
            "alpha": None,
        },
        {
            "key": "negbin",
            "name": "Negative binomial",
            "family": "count regression",
            "mae": nb_scores["mae"],
            "rmse": nb_scores["rmse"],
            "aic": int(round(nb_aic)),
            "alpha": round(alpha, 3),
        },
        {
            "key": "ets",
            "name": "Holt–Winters",
            "family": "time series",
            "mae": ets_scores["mae"],
            "rmse": ets_scores["rmse"],
            "aic": None,
            "alpha": None,
        },
    ]

    def explained(model: Any) -> float:
        return float(100.0 * (1.0 - model.deviance / model.null_deviance))

    calendar_share = float(explained(calendar_model))
    weather_share = float(explained(weather_model))
    joint_share = float(explained(mean_model))
    pearson_dispersion = float(mean_model.pearson_chi2 / mean_model.df_resid)
    variance_ratio = float(operating["count"].var() / operating["count"].mean())

    profiles = {
        "all": _hour_profile(operating),
        "weekday": _hour_profile(operating[operating["weekend"] == 0]),
        "weekend": _hour_profile(operating[operating["weekend"] == 1]),
    }
    peak_hour = int(np.argmax(profiles["all"]))
    top_hours = sorted(
        ({"hour": h, "rides": profiles["all"][h]} for h in range(24)),
        key=lambda row: row["rides"],
        reverse=True,
    )[:6]

    weekday = operating[operating["weekend"] == 0]
    weekend = operating[operating["weekend"] == 1]

    def commute_share(frame: pd.DataFrame) -> float:
        share = (
            100.0
            * frame[frame["hour"].isin(COMMUTE_HOURS)]["count"].sum()
            / frame["count"].sum()
        )
        return round(float(share), 1)

    holiday_mean = float(operating[operating["holiday_flag"] == 1]["count"].mean())
    normal_mean = float(operating[operating["holiday_flag"] == 0]["count"].mean())

    monthly_raw = (
        operating.assign(month=operating["date"].dt.month)
        .groupby("month")
        .agg(total=("count", "sum"), days=("date", "nunique"))
    )
    months = [
        {
            "month": int(month),
            "total": int(row["total"]),
            "days": int(row["days"]),
            "per_day": int(round(row["total"] / row["days"])),
        }
        for month, row in monthly_raw.iterrows()
    ]
    busiest = max(months, key=lambda row: row["per_day"])
    quietest = min(months, key=lambda row: row["per_day"])

    season_raw = (
        operating.groupby("season")
        .agg(total=("count", "sum"), days=("date", "nunique"), mean=("count", "mean"))
        .reindex(SEASONS)
    )
    seasons = [
        {
            "season": season,
            "per_day": int(round(row["total"] / row["days"])),
            "mean_hourly": round(float(row["mean"]), 1),
        }
        for season, row in season_raw.iterrows()
    ]

    rainy_hours = int((operating["rain"] > 0).sum())
    sample = train.sample(n=min(2000, len(train)), random_state=7)

    # Compare, for each observed temperature band, the actual mean with the
    # model's mean over the same rows. This avoids extrapolating warm weather
    # into winter hours, which a global partial-dependence curve would do.
    temp_bins = pd.cut(operating["temp"], np.arange(-16, 40, 4))
    observed = operating.groupby(temp_bins, observed=True)["count"].agg(
        ["mean", "size"]
    )
    observed = observed[observed["size"] >= 15]
    temp_centers = [round(float(interval.mid), 1) for interval in observed.index]
    temp_predicted = []
    for interval in observed.index:
        rows = train[
            train["temp"].between(interval.left, interval.right, inclusive="right")
        ]
        temp_predicted.append(
            round(float(mean_model.predict(rows).mean()), 1) if len(rows) else 0.0
        )
    temp_observed = {
        "temps": temp_centers,
        "rides": [round(float(value), 1) for value in observed["mean"]],
        "counts": [int(value) for value in observed["size"]],
    }

    rain_mm = [0, 1, 2, 5, 10, 20]
    rain_rides = [
        int(
            round(
                float(mean_model.predict(sample.assign(log_rain=np.log1p(mm))).mean())
            )
        )
        for mm in rain_mm
    ]
    rain_curve = [
        {
            "mm": mm,
            "rides": rides,
            "drop_pct": round(100.0 * (1.0 - rides / rain_rides[0]), 1),
        }
        for mm, rides in zip(rain_mm, rain_rides)
    ]

    season_stats = {}
    for season in SEASONS:
        frame = operating[operating["season"] == season]
        solar = frame.groupby("hour")["solar"].mean().reindex(range(24), fill_value=0.0)
        season_stats[season] = {
            "temp": round(float(frame["temp"].median()), 1),
            "humidity": round(float(frame["humidity"].median()), 1),
            "wind": round(float(frame["wind"].median()), 2),
            "visibility": round(float(frame["visibility"].median()), 0),
            "solar": [round(float(value), 2) for value in solar],
        }

    mae_gain = round(100.0 * (1.0 - nb_scores["mae"] / ets_scores["mae"]), 1)
    rmse_gain = round(100.0 * (1.0 - nb_scores["rmse"] / ets_scores["rmse"]), 1)

    payload = {
        "meta": {
            "dataset": "UCI Seoul Bike Sharing Demand",
            "source": "https://archive.ics.uci.edu/dataset/560/seoul+bike+sharing+demand",
            "start": operating["date"].min().strftime("%Y-%m-%d"),
            "end": operating["date"].max().strftime("%Y-%m-%d"),
            "rows": int(len(data)),
            "operating_hours": int(len(operating)),
            "closed_hours": int(len(data) - len(operating)),
            "days": int(operating["date"].nunique()),
            "rides": int(operating["count"].sum()),
            "avg_hourly": round(float(operating["count"].mean()), 1),
            "avg_daily": int(round(operating.groupby("date")["count"].sum().mean())),
            "peak_hour": peak_hour,
            "peak_mean": profiles["all"][peak_hour],
            "min_mean": min(profiles["all"]),
            "max_count": int(operating["count"].max()),
        },
        "profiles": profiles,
        "peaks": {
            "peak_hour": peak_hour,
            "top_hours": top_hours,
            "weekday_commute_share": commute_share(weekday),
            "weekend_commute_share": commute_share(weekend),
            "holiday_mean": round(holiday_mean, 1),
            "normal_mean": round(normal_mean, 1),
            "holiday_gap": round(100.0 * (1.0 - holiday_mean / normal_mean), 1),
            "morning_peak": profiles["weekday"][8],
            "evening_peak": profiles["weekday"][18],
            "evening_gap": round(
                100.0 * (profiles["weekday"][18] / profiles["weekday"][8] - 1.0), 1
            ),
        },
        "calendar": {
            "month_hour": _matrix(
                operating.assign(month=operating["date"].dt.month),
                "month",
                list(range(1, 13)),
            ),
            "weekday_hour": _matrix(
                operating.assign(weekday=operating["date"].dt.day_of_week),
                "weekday",
                list(range(7)),
            ),
            "months": months,
            "seasons": seasons,
            "busiest_month": busiest,
            "quietest_month": quietest,
            "rainy_hours": rainy_hours,
            "rainy_share": round(100.0 * rainy_hours / len(operating), 1),
        },
        "weather": {
            "temp_curve": {
                "temps": temp_centers,
                "predicted": temp_predicted,
                "observed": temp_observed,
                "peak_temp": float(
                    temp_centers[int(np.argmax(temp_observed["rides"]))]
                ),
            },
            "rain_curve": rain_curve,
            "deviance": {
                "calendar": round(float(calendar_share), 1),
                "weather": round(float(weather_share), 1),
                "full": round(float(joint_share), 1),
                "weather_unique": round(float(joint_share - calendar_share), 1),
                "calendar_unique": round(float(joint_share - weather_share), 1),
            },
            "pearson_dispersion": round(pearson_dispersion, 1),
            "variance_ratio": round(variance_ratio, 1),
        },
        "models": {
            "metrics": metrics,
            "improvement": {"mae": mae_gain, "rmse": rmse_gain},
            "test": {
                "start": test["date"].min().strftime("%Y-%m-%d"),
                "end": test["date"].max().strftime("%Y-%m-%d"),
                "hours": int(len(test)),
                "timestamps": [
                    stamp.strftime("%Y-%m-%dT%H:%M") for stamp in test["timestamp"]
                ],
                "actual": [int(value) for value in actual],
                "poisson": [int(round(value)) for value in predicted],
                "negbin": [int(round(value)) for value in predicted],
                "ets": [int(round(value)) for value in ets_test],
            },
        },
        "simulator": {
            "default": {
                "hour": 18,
                "season": "Spring",
                "weekend": False,
                "holiday": False,
                "temperature": 18.0,
                "humidity": 55.0,
                "rainfall": 0.0,
            },
            "seasons": season_stats,
        },
        "method": {
            "alpha": round(alpha, 3),
            "poisson_aic": int(round(mean_model.aic)),
            "nb_aic": int(round(nb_aic)),
            "aic_gap": int(round(mean_model.aic - nb_aic)),
            "parameters": int(n_params),
            "train_hours": int(len(train)),
            "test_hours": int(len(test)),
            "test_days": TEST_DAYS,
            "dispersion": round(pearson_dispersion, 1),
            "variance_ratio": round(variance_ratio, 1),
        },
    }

    return Bundle(
        data=data,
        train=train,
        test=test,
        mean_model=mean_model,
        ets=ets,
        alpha=alpha,
        overdispersed=pearson_dispersion > 1.0,
        metrics=metrics,
        season_stats=season_stats,
        payload=payload,
    )


def predict(bundle: Bundle, request: dict) -> dict:
    season = request["season"]
    stats = bundle.season_stats[season]
    weekend = int(bool(request["weekend"]))
    holiday = int(bool(request["holiday"]))
    rainfall = float(request["rainfall"])
    temperature = float(request["temperature"])
    humidity = float(request["humidity"])

    def rows(temp: float, humid: float, rain: float, holiday_flag: int) -> list[dict]:
        output = []
        for hour in range(24):
            solar = stats["solar"][hour] * (0.35 if rain > 0 else 1.0)
            output.append(
                {
                    "hour": hour,
                    "weekend": weekend,
                    "season": season,
                    "holiday_flag": holiday_flag,
                    "temp": temp,
                    "humidity": humid,
                    "wind": stats["wind"],
                    "visibility": stats["visibility"],
                    "log_solar": float(np.log1p(solar)),
                    "log_rain": float(np.log1p(rain)),
                    "snow": 0.0,
                }
            )
        return output

    mean_model = bundle.mean_model
    day = mean_model.predict(
        pd.DataFrame(rows(temperature, humidity, rainfall, holiday))
    )
    typical_day = mean_model.predict(
        pd.DataFrame(rows(stats["temp"], stats["humidity"], 0.0, 0))
    )
    expected = float(day[int(request["hour"])])
    typical = float(typical_day[int(request["hour"])])

    if bundle.overdispersed:
        size = 1.0 / bundle.alpha
        prob = size / (size + expected)
        low, high = nbinom.ppf([0.1, 0.9], size, prob)
    else:
        low, high = poisson.ppf([0.1, 0.9], expected)

    return {
        "hour": int(request["hour"]),
        "season": season,
        "prediction": int(round(expected)),
        "typical": int(round(typical)),
        "delta_pct": round(100.0 * (expected / typical - 1.0), 1) if typical else 0.0,
        "interval": [max(0, int(round(low))), int(round(high))],
        "day": [int(round(value)) for value in day],
        "typical_day": [int(round(value)) for value in typical_day],
        "model": "Negative binomial" if bundle.overdispersed else "Poisson",
        "alpha": round(bundle.alpha, 3),
    }
