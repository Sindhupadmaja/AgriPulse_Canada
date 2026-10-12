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
    assert parse_measure("Average yield (bushels per acre)", "Bushels per acre") == ("yield", "bu_ac", "imperial")
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
