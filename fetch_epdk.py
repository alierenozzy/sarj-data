#!/usr/bin/env python3
"""EPDK Serbest Erişim Platformu'ndan halka açık şarj istasyonlarını çekip stations.json üretir.

EPDK servisi alışılmadık şekilde GET isteğiyle birlikte JSON gövde bekler ({} = filtresiz, tüm
istasyonlar). Kota çok dardır: arka arkaya ikinci istek 429 döner. Bu yüzden her çalıştırma tam
olarak BİR istek atar ve asla tekrar denemez. Android uygulama EPDK'yı değil, yayınlanan dosyayı
okur.

Kullanım:
    fetch_epdk.py                         EPDK'dan çek, data/stations.json yaz
    fetch_epdk.py --save-raw raw.json     ham yanıtı da sakla (hata ayıklama için)
    fetch_epdk.py --from-raw raw.json     kayıtlı yanıttan üret, istek atma
    fetch_epdk.py --out yol/stations.json çıktı yolunu değiştir
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://apigateway.epdk.gov.tr/sarjIstasyonlari"
USER_AGENT = "EnUcuzSarj-data/1.0"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "stations.json"
ALIASES = ROOT / "data" / "brand_aliases.json"

MIN_STATIONS = 5000          # bugün ~13 bin halka açık istasyon var; altı bozuk yanıt demektir
MIN_SHARE_OF_PREVIOUS = 0.9  # bir günde %10'dan fazla düşüş varsa yayınlama
TURKEY_BOX = (35.0, 43.0, 25.0, 45.0)  # lat_min, lat_max, lng_min, lng_max


class FeedUnavailable(Exception):
    """Kota (429) veya EPDK kesintisi (5xx / ağ hatası): rutin, ertesi gün tekrar denenir."""


def fetch() -> object:
    req = urllib.request.Request(
        URL, data=b"{}", method="GET",
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 429 or e.code >= 500:
            raise FeedUnavailable(f"HTTP {e.code}") from e
        raise  # diğer 4xx: servis değişmiş olabilir, bir insanın bakması gerek
    except (urllib.error.URLError, TimeoutError) as e:
        raise FeedUnavailable(str(e)) from e


# --- yardımcılar -------------------------------------------------------------------------------

_TR = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")


def slug(text: str) -> str:
    """'Eşarj' -> 'esarj', 'WAT Mobilite' -> 'wat-mobilite'. Fiyat tablosuyla eşleştirme anahtarı."""
    text = (text or "").translate(_TR)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def number(value) -> float | None:
    if isinstance(value, str):
        value = value.replace(",", ".").strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def in_turkey(lat, lng) -> bool:
    a, b, c, d = TURKEY_BOX
    return lat is not None and lng is not None and a <= lat <= b and c <= lng <= d


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"evet", "true", "1", "e", "yes"}


_ADDR_TAIL = re.compile(r"([^\s/][^/]*?)\s*/\s*([^/]+?)\s*$")


def split_city(address: str) -> tuple[str | None, str | None]:
    """EPDK adresleri genelde '... Arnavutköy / İSTANBUL' ile biter. (ilçe, il) döndürür."""
    m = _ADDR_TAIL.search(address or "")
    if not m:
        return None, None
    district = m.group(1).split()[-1] if m.group(1).split() else None
    return district, tr_upper(m.group(2).strip()) or None


def tr_upper(text: str) -> str:
    return text.replace("i", "İ").replace("ı", "I").upper()


def classify_socket(sock: dict) -> dict | None:
    kind = (sock.get("soketTuru") or "").strip()
    tip = (sock.get("soketTipi") or "").strip().upper()
    kw = number(sock.get("soketGucu"))
    up = kind.upper()
    if "CHADEMO" in up:
        current, standard = "DC", "CHAdeMO"
    elif tip == "DC" or up.startswith("DC") or "CCS" in up:
        current, standard = "DC", "CCS" if ("CCS" in up or not kind) else kind
    else:
        current = "AC"
        standard = "Type 2" if ("TYPE" in up or "TİP" in up or "TIP" in up or not kind) else kind
    return {"type": current, "standard": standard, "kw": round(kw) if kw else None}


def load_aliases() -> dict[str, str]:
    if not ALIASES.exists():
        return {}
    raw = json.loads(ALIASES.read_text(encoding="utf-8"))
    return {slug(k): v for k, v in raw.get("aliases", {}).items()}


def station(rec: dict, aliases: dict[str, str]) -> dict | None:
    code = (rec.get("sarjIstasyonuNo") or "").strip()
    lat, lng = number(rec.get("enlem")), number(rec.get("boylam"))
    if not code or not in_turkey(lat, lng):
        return None

    sockets = [s for s in map(classify_socket, rec.get("soketler") or []) if s]
    ac = [s["kw"] or 0 for s in sockets if s["type"] == "AC"]
    dc = [s["kw"] or 0 for s in sockets if s["type"] == "DC"]

    brand = " ".join((rec.get("marka") or "").split())
    key = slug(brand)
    key = aliases.get(key, key)
    address = " ".join((rec.get("adres") or "").split())
    district, city = split_city(address)
    name = " ".join((rec.get("sarjIstasyonuAdi") or "").split())

    # Not: 'sarjIstasyonuIsletmecisi' kişi adı içerebildiği için (KVKK) bilinçli olarak alınmıyor.
    return {
        "id": code,
        "name": name or f"{brand} Şarj Noktası",
        "brand": brand,
        "brandKey": key,
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "address": address,
        "city": city,
        "district": district,
        "green": truthy(rec.get("yesilSarjIstasyonuMu")),
        "sockets": sockets,
        "acCount": len(ac),
        "acMaxKw": max(ac) or None if ac else None,
        "dcCount": len(dc),
        "dcMaxKw": max(dc) or None if dc else None,
    }


def build(feed: object, aliases: dict[str, str]) -> tuple[list[dict], dict]:
    records = feed.get("data") if isinstance(feed, dict) else feed
    if not isinstance(records, list):
        raise ValueError(f"Beklenmeyen yanıt yapısı: {str(feed)[:300]}")
    public = [r for r in records
              if (r.get("hizmetSekli") or "").strip().casefold().startswith("halka")]
    stations = sorted(filter(None, (station(r, aliases) for r in public)), key=lambda s: s["id"])
    stats = {"feedRecords": len(records), "public": len(public), "placeable": len(stations)}
    return stations, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save-raw", type=Path)
    ap.add_argument("--from-raw", type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--min-stations", type=int, default=MIN_STATIONS)
    args = ap.parse_args()

    if args.from_raw:
        feed = json.loads(args.from_raw.read_text(encoding="utf-8"))
    else:
        try:
            feed = fetch()
        except FeedUnavailable as e:
            # Kota/kesinti: mevcut dosyayı koru, işi başarısız sayma. Bayatlama kontrolü workflow'da.
            print(f"EPDK şu an kullanılamıyor ({e}); mevcut veri korunuyor.")
            return 0
        if args.save_raw:
            args.save_raw.write_text(json.dumps(feed, ensure_ascii=False), encoding="utf-8")

    stations, stats = build(feed, load_aliases())
    print(f"EPDK: {stats['feedRecords']} kayıt, {stats['public']} halka açık, "
          f"{stats['placeable']} haritaya yerleşebilir")

    if len(stations) < args.min_stations:
        print(f"HATA: yalnızca {len(stations)} istasyon; yayınlanmıyor", file=sys.stderr)
        return 1
    if args.out.exists():
        prev = json.loads(args.out.read_text(encoding="utf-8")).get("stations", [])
        if len(stations) < len(prev) * MIN_SHARE_OF_PREVIOUS:
            print(f"HATA: {len(stations)} istasyon, önceki {len(prev)}; yayınlanmıyor",
                  file=sys.stderr)
            return 1
        if prev == stations:
            print("Veri değişmedi; dosyaya dokunulmadı.")
            return 0

    out = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": URL,
        "count": len(stations),
        "stations": stations,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(args.out)
    print(f"Yazıldı: {args.out} ({len(stations)} istasyon)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
