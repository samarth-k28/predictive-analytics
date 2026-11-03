def test_overdispersion_is_detected(bundle):
    weather = bundle.payload["weather"]
    assert weather["pearson_dispersion"] > 10
    assert weather["variance_ratio"] > 100
    assert bundle.overdispersed is True
    assert 0.05 < bundle.alpha < 2.0


def test_poisson_and_nb_share_the_mean(bundle):
    metrics = {row["key"]: row for row in bundle.metrics}
    assert metrics["poisson"]["mae"] == metrics["negbin"]["mae"]
    assert metrics["poisson"]["rmse"] == metrics["negbin"]["rmse"]
    assert metrics["negbin"]["aic"] < metrics["poisson"]["aic"]


def test_count_model_beats_the_time_series_baseline(bundle):
    metrics = {row["key"]: row for row in bundle.metrics}
    assert metrics["negbin"]["mae"] < 0.75 * metrics["ets"]["mae"]
    assert metrics["negbin"]["rmse"] < 0.75 * metrics["ets"]["rmse"]
    assert bundle.payload["models"]["improvement"]["mae"] > 40


def test_peak_hour_profile(bundle):
    peaks = bundle.payload["peaks"]
    profiles = bundle.payload["profiles"]
    assert peaks["peak_hour"] == 18
    assert peaks["peak_hour"] in {row["hour"] for row in peaks["top_hours"]}
    assert profiles["weekday"][18] > profiles["weekday"][8] > profiles["weekday"][4]
    assert peaks["weekday_commute_share"] > peaks["weekend_commute_share"]
    assert peaks["holiday_mean"] < peaks["normal_mean"]
    assert peaks["evening_gap"] > 0


def test_deviance_decomposition(bundle):
    deviance = bundle.payload["weather"]["deviance"]
    assert deviance["calendar"] > deviance["weather"] > 50
    assert deviance["full"] < 100
    assert deviance["weather_unique"] > 0
    assert deviance["calendar_unique"] > deviance["weather_unique"]


def test_test_series_are_aligned(bundle):
    test = bundle.payload["models"]["test"]
    assert test["hours"] == 336
    for key in ("timestamps", "actual", "poisson", "negbin", "ets"):
        assert len(test[key]) == test["hours"]
    assert test["poisson"] == test["negbin"]


def test_weather_curves(bundle):
    weather = bundle.payload["weather"]
    curve = weather["temp_curve"]
    assert len(curve["temps"]) == len(curve["predicted"])
    assert len(curve["observed"]["temps"]) == len(curve["observed"]["rides"])
    assert 20 <= curve["peak_temp"] <= 30
    assert weather["rain_curve"][0]["drop_pct"] == 0
    assert weather["rain_curve"][-1]["drop_pct"] > 90


def test_calendar_matrices(bundle):
    calendar = bundle.payload["calendar"]
    assert len(calendar["month_hour"]) == 12
    assert all(len(row) == 24 for row in calendar["month_hour"])
    assert len(calendar["weekday_hour"]) == 7
    assert all(len(row) == 24 for row in calendar["weekday_hour"])
    assert calendar["busiest_month"]["month"] == 6
    assert calendar["quietest_month"]["month"] == 1
