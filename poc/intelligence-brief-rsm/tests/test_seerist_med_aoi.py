"""MED-specific multi-country aoiId parameterisation."""
from unittest.mock import MagicMock


def test_aoi_param_for_region_med():
    """MED resolves to a comma-separated ISO-2 country list, not 'MENA'."""
    from tools.seerist_client import _aoi_param_for_region
    assert _aoi_param_for_region("MED") == "IT,ES,GR,TR,MA,EG"


def test_aoi_param_for_region_passthrough_for_direct_regions():
    """APAC/AME still resolve directly to their Seerist AoIs."""
    from tools.seerist_client import _aoi_param_for_region
    assert _aoi_param_for_region("APAC") == "APAC"
    assert _aoi_param_for_region("AME") == "AMER"


def test_get_events_uses_country_list_for_med():
    """get_events('MED', …) sends aoiId='IT,ES,GR,TR,MA,EG' upstream."""
    from tools.seerist_client import SeeristClient
    client = SeeristClient.__new__(SeeristClient)
    client._client = MagicMock()
    client._client.get.return_value.json.return_value = {"features": []}
    client._client.get.return_value.raise_for_status = MagicMock()

    client.get_events("MED", days=7)

    args, kwargs = client._client.get.call_args
    assert kwargs["params"]["aoiId"] == "IT,ES,GR,TR,MA,EG"


def test_iso2_normalizer_handles_both_endpoint_schemas():
    """_feature_country_iso2 maps cluster (nested ISO-2) and WoD (top-level
    ISO-3) to the same ISO-2 representation. Confirms why the filter set
    only needs ISO-2."""
    from tools.seerist_client import _feature_country_iso2
    cluster = {"properties": {"location_metadata": {"countryCode": "IT"}}}
    wod = {"properties": {"countryCode": "ITA"}}
    assert _feature_country_iso2(cluster) == "IT"
    assert _feature_country_iso2(wod) == "IT"
