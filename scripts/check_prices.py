#!/usr/bin/env python3
"""prices.json'u doğrular ve stations.json ile eşleşme oranını raporlar.

    check_prices.py [--stations data/stations.json] [--prices data/prices.json] [--max-age-days 45]

Hata varsa (bozuk aralık, absürt fiyat) 1 ile çıkar. Fiyat yaşı ve kapsam yalnızca uyarıdır.
"""
import argparse
import collections
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANE = (3.0, 30.0)  # TL/kWh; bunun dışı büyük ihtimalle yazım hatası


def check(prices: dict, max_age_days: int) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    today = dt.date.today()
    for key, b in prices["brands"].items():
        if b.get("ac") is None and b.get("dc") is None:
            errors.append(f"{key}: ne AC ne DC fiyatı var (kaydı silin)")
        for kind in ("ac", "dc"):
            r = b.get(kind)
            if r is None:
                continue
            lo, hi = r.get("min"), r.get("max")
            if lo is None or hi is None or lo > hi:
                errors.append(f"{key}.{kind}: geçersiz aralık {r}")
            elif not (SANE[0] <= lo and hi <= SANE[1]):
                errors.append(f"{key}.{kind}: makul dışı fiyat {r}")
        if b.get("confidence") not in {"high", "medium", "low"}:
            errors.append(f"{key}: confidence eksik/geçersiz")
        checked = b.get("checkedAt")
        if checked and (today - dt.date.fromisoformat(checked)).days > max_age_days:
            warnings.append(f"{key}: fiyat {checked} tarihinden beri kontrol edilmedi")
    return errors, warnings


def coverage(stations: list[dict], prices: dict) -> None:
    known = set(prices["brands"])
    by_brand = collections.Counter(s["brandKey"] for s in stations)
    priced = sum(n for k, n in by_brand.items() if k in known)
    conf = collections.Counter()
    for k, n in by_brand.items():
        if k in known:
            conf[prices["brands"][k]["confidence"]] += n
    total = len(stations)
    print(f"Fiyatı bilinen istasyon: {priced}/{total} (%{100 * priced / total:.1f})")
    for c in ("high", "medium", "low"):
        print(f"  {c:6}: {conf[c]:5d} (%{100 * conf[c] / total:.1f})")
    missing = [(k, n) for k, n in by_brand.most_common() if k not in known][:15]
    print("Fiyatı olmayan en büyük markalar:", ", ".join(f"{k} ({n})" for k, n in missing))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stations", type=Path, default=ROOT / "data" / "stations.json")
    ap.add_argument("--prices", type=Path, default=ROOT / "data" / "prices.json")
    ap.add_argument("--max-age-days", type=int, default=45)
    args = ap.parse_args()

    prices = json.loads(args.prices.read_text(encoding="utf-8"))
    errors, warnings = check(prices, args.max_age_days)
    for w in warnings:
        print("UYARI:", w)
    if args.stations.exists():
        coverage(json.loads(args.stations.read_text(encoding="utf-8"))["stations"], prices)
    for e in errors:
        print("HATA:", e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
