import pandas as pd


def test_raw_dataset_shape(bundle):
    assert len(bundle.data) == 8760
    assert bundle.data["operating"].sum() == 8465
    assert (~bundle.data["operating"]).sum() == 295
    assert bundle.data["timestamp"].is_monotonic_increasing
    assert not bundle.data["timestamp"].duplicated().any()


def test_closed_hours_are_zero(bundle):
    closed = bundle.data[~bundle.data["operating"]]
    assert (closed["count"] == 0).all()


def test_split_is_fourteen_days(bundle):
    assert len(bundle.test) == 336
    assert bundle.test["date"].nunique() == 14
    assert bundle.test["date"].min() == pd.Timestamp("2018-11-17")
    assert bundle.test["date"].max() == pd.Timestamp("2018-11-30")
    assert len(bundle.train) + len(bundle.test) == 8465
