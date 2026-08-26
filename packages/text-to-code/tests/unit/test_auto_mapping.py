from text_to_code.services.auto_mapping import convert_known_code, get_auto_mapping


class TestGetAutoMapping:
    def test_loads_auto_mapping(self) -> None:
        auto_mapping: dict[str, str] = get_auto_mapping()

        assert auto_mapping["HGB"] == "Hgb Bld-mCnc"
        assert auto_mapping["HGB."] == "Hgb Bld-mCnc"
        assert auto_mapping["POC Glucose"] == "Glucose [Mass/Volume] in Blood"

    def test_contains_identity_mapping(self) -> None:
        auto_mapping: dict[str, str] = get_auto_mapping()

        assert "FIO2" in auto_mapping
        assert auto_mapping["FIO2"] == "FIO2"

    def test_returns_cached_mapping(self) -> None:
        first_mapping: dict[str, str] = get_auto_mapping()
        second_mapping: dict[str, str] = get_auto_mapping()

        assert first_mapping is second_mapping


class TestConvertKnownCode:
    def test_converts_known_nonstandard_input(self) -> None:
        result: str = convert_known_code("HGB")

        assert result == "Hgb Bld-mCnc"

    def test_converts_known_nonstandard_input_with_punctuation(self) -> None:
        result: str = convert_known_code("=>BLOOD CULTURE<=")

        assert result == "Bacteria identified in Blood by Culture"

    def test_returns_original_input_when_mapping_does_not_exist(self) -> None:
        result: str = convert_known_code("completely unknown lab value")

        assert result == "completely unknown lab value"

    def test_mapping_is_case_sensitive(self) -> None:
        result: str = convert_known_code("hgb")

        assert result == "hgb"

    def test_returns_identity_mapping_unchanged(self) -> None:
        result: str = convert_known_code("FIO2")

        assert result == "FIO2"
