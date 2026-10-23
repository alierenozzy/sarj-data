"""fetch_epdk.py için ağ gerektirmeyen testler. Çalıştır: python3 scripts/test_fetch_epdk.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_epdk as f  # noqa: E402


def rec(**kw):
    base = {
        "sarjIstasyonuNo": "ŞRJ/1", "sarjIstasyonuAdi": "Test AVM", "marka": "Eşarj",
        "hizmetSekli": "Halka Açık", "enlem": "39.92", "boylam": "32.85",
        "adres": "Kızılay Mahallesi No:1 Çankaya / ANKARA", "yesilSarjIstasyonuMu": "Evet",
        "soketler": [
            {"soketTipi": "AC", "soketTuru": "Type 2", "soketGucu": "22"},
            {"soketTipi": "DC", "soketTuru": "CCS", "soketGucu": "120"},
            {"soketTipi": "DC", "soketTuru": "CHAdeMO", "soketGucu": "50"},
        ],
    }
    base.update(kw)
    return base


class Tests(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(f.slug("Eşarj"), "esarj")
        self.assertEqual(f.slug("WAT Mobilite"), "wat-mobilite")
        self.assertEqual(f.slug("5 ŞARJ"), "5-sarj")
        self.assertEqual(f.slug("Otopriz"), "otopriz")

    def test_station_fields(self):
        s = f.station(rec(), {})
        self.assertEqual(s["brandKey"], "esarj")
        self.assertEqual((s["district"], s["city"]), ("Çankaya", "ANKARA"))
        self.assertTrue(s["green"])
        self.assertEqual((s["acCount"], s["acMaxKw"], s["dcCount"], s["dcMaxKw"]), (1, 22, 2, 120))
        self.assertEqual(s["sockets"][2]["standard"], "CHAdeMO")
        self.assertNotIn("sarjIstasyonuIsletmecisi", s)

    def test_comma_decimal_and_bad_coords(self):
        self.assertIsNotNone(f.station(rec(enlem="39,92", boylam="32,85"), {}))
        self.assertIsNone(f.station(rec(enlem="0", boylam="0"), {}))
        self.assertIsNone(f.station(rec(sarjIstasyonuNo=""), {}))

    def test_alias(self):
        s = f.station(rec(marka="E-ŞARJ"), {"e-sarj": "esarj"})
        self.assertEqual(s["brandKey"], "esarj")

    def test_build_filters_private(self):
        feed = {"data": [rec(), rec(sarjIstasyonuNo="ŞRJ/2", hizmetSekli="Özel")]}
        stations, stats = f.build(feed, {})
        self.assertEqual(len(stations), 1)
        self.assertEqual(stats["public"], 1)

    def test_build_accepts_bare_list(self):
        stations, _ = f.build([rec()], {})
        self.assertEqual(len(stations), 1)

    def test_lowercase_city(self):
        self.assertEqual(f.split_city("x No:3 Merkez / izmir")[1], "İZMİR")


if __name__ == "__main__":
    unittest.main(verbosity=1)
