import pytest

from src.standardize import SchemaError, clean_label, detect_columns, name_key, parse_measure


def test_parse_measure_metric_units():
    assert parse_measure("Production (metric tonnes)", "Metric tonnes") == ("production", "tonnes", "metric")
    assert parse_measure("Harvested area (hectares)", "Hectares") == ("harvested_area", "hectares", "metric")
    assert parse_measure("Average yield (kilograms per hectare)", "Kilograms per hectare") == ("yield", "kg_ha", "metric")
    assert parse_measure("Average farm price (dollars per tonne)", "Dollars per tonne") == ("farm_price", "dollars_per_tonne", "metric")
    assert parse_measure("Total farm value (dollars)", "Dollars") == ("farm_value", "dollars", "neutral")


def test_parse_measure_imperial_and_unknown():
    assert parse_measure("Seeded area (acres)", "Acres") == ("seeded_area", "acres", "imperial")
    assert parse_measure("Average yield (bushels per acre)", "Bushels per acre") == ("yield", "bushels_per_acre", "imperial")
    assert parse_measure("Something else", "Units") == (None, None, None)


def test_clean_label_and_key():
    assert clean_label("  Wheat,   all [1] ") == "Wheat, all"
    assert name_key("Wheat, all") == name_key("wheat,  ALL ")


def test_detect_columns_requires_contract():
    ok = ["REF_DATE", "GEO", "Harvest disposition", "Type of crop", "UOM", "VALUE", "STATUS"]
    cols = detect_columns(ok)
    assert cols["measure"] == "Harvest disposition" and cols["crop"] == "Type of crop"
    with pytest.raises(SchemaError):
        detect_columns(["REF_DATE", "GEO", "Harvest disposition", "UOM", "VALUE"])


# The exact measure/unit labels found in the real Statistics Canada file (profile of table 32-10-0359-01).
REAL_LABELS = [
    ("Average farm price (dollars per bushel)", "Dollars per bushel"),
    ("Average farm price (dollars per hundredweight)", "Dollars per hundredweight"),
    ("Average farm price (dollars per pound)", "Dollars per pound"),
    ("Average farm price (dollars per ton)", "Dollars per ton"),
    ("Average farm price (dollars per tonne)", "Dollars per tonne"),
    ("Average yield (bushels per acre)", "Bushels per acre"),
    ("Average yield (hundredweight per acre)", "Hundredweight per acre"),
    ("Average yield (kilograms per hectare)", "Kilograms per hectare"),
    ("Average yield (pounds per acre)", "Pounds per acre"),
    ("Average yield (tons per acre)", "Tons per acre"),
    ("Harvested area (acres)", "Acres"),
    ("Harvested area (hectares)", "Hectares"),
    ("Production (bushels)", "Bushels"),
    ("Production (hundredweight)", "Hundredweight"),
    ("Production (metric tonnes)", "Metric tonnes"),
    ("Production (pounds)", "Pounds"),
    ("Production (tons)", "Tons"),
    ("Seeded area (acres)", "Acres"),
    ("Seeded area (hectares)", "Hectares"),
    ("Total farm value (dollars)", "Dollars"),
]


def test_real_labels_load_exactly_six_metric_measures_and_never_collide():
    from src import config
    parsed = [parse_measure(m, u) for m, u in REAL_LABELS]
    assert all(p[0] is not None for p in parsed)                       # nothing unmapped
    loaded = {(m, unit) for m, unit, _ in parsed if (m, unit) in config.FACT_UNITS}
    assert loaded == config.FACT_UNITS                                  # all six metric measures found
    assert len({(m, unit) for m, unit, _ in parsed}) == len(REAL_LABELS)  # no two labels share a code
    assert parse_measure("Production (tons)", "Tons")[2] == "imperial"  # short tons are not metric tonnes
