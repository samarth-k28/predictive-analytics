BASE = {
    "hour": 18,
    "season": "Spring",
    "weekend": False,
    "holiday": False,
    "temperature": 18,
    "humidity": 55,
    "rainfall": 0,
}


def post(client, **overrides):
    return client.post("/api/predict", json={**BASE, **overrides})


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard(client):
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["rides"] > 6_000_000
    assert payload["models"]["test"]["hours"] == 336
    assert len(payload["profiles"]["all"]) == 24


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Seoul" in response.text
    assert 'data-theme="dark"' in response.text
    assert 'href="/report"' in response.text


def test_report_page(client):
    response = client.get("/report")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Probable viva questions" in response.text
    assert "Negative binomial" in response.text


def test_prediction_shape(client):
    response = post(client)
    assert response.status_code == 200
    result = response.json()
    assert result["prediction"] > 0
    assert result["interval"][0] <= result["prediction"] <= result["interval"][1]
    assert len(result["day"]) == 24
    assert len(result["typical_day"]) == 24
    assert result["day"][18] == result["prediction"]
    assert result["model"] == "Negative binomial"


def test_rain_lowers_demand(client):
    dry = post(client, rainfall=0).json()["prediction"]
    wet = post(client, rainfall=10).json()["prediction"]
    assert wet < dry * 0.5


def test_warmer_spring_hour_is_busier(client):
    cold = post(client, hour=8, temperature=0).json()["prediction"]
    warm = post(client, hour=8, temperature=20).json()["prediction"]
    assert warm > cold


def test_weekend_changes_the_evening_peak(client):
    weekday = post(client, weekend=False).json()["prediction"]
    weekend = post(client, weekend=True).json()["prediction"]
    assert weekday > weekend


def test_invalid_payloads_are_rejected(client):
    assert post(client, hour=24).status_code == 422
    assert post(client, season="Monsoon").status_code == 422
    assert post(client, humidity=120).status_code == 422
    assert post(client, unexpected=True).status_code == 422
