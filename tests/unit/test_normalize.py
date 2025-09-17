from utils import normalize as utils


class TestNormalizeText:
    def test_normalize_text(self):
        text = " Cell growth [Presence] of Amniocytes Qualitative by Tissue culture"
        assert (
            utils.normalize_text(text)
            == "cell growth presence of amniocytes qualitative by tissue culture"
        )

        text = "Power spectrum.theta frequency/Power spectrum.total"
        assert utils.normalize_text(text) == "power spectrum theta frequency power spectrum total"

        text = "VFr.DF"
        assert utils.normalize_text(text) == "vfr df"
