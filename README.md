# En Ucuz Şarj — veri hattı

Android uygulamanın okuduğu iki dosyayı üretir:

| Dosya | İçerik | Nereden | Ne sıklıkla |
|---|---|---|---|
| `data/stations.json` | Halka açık tüm şarj istasyonları: konum, adres, il/ilçe, soketler (AC/DC, standart, kW), marka | EPDK Serbest Erişim Platformu API'si | Her gece otomatik |
| `data/prices.json` | Operatör bazlı AC/DC fiyatları (TL/kWh, KDV dahil), kaynak ve güven seviyesi | Operatörlerin resmi sayfaları + agregatörler | Elle (şimdilik) |
| `data/meta.json` | Sürüm hash'leri, istasyon sayısı | Workflow | Her değişimde |

Uygulama önce `meta.json`'u indirir; hash değişmişse ilgili dosyayı yeniden çeker.

## Kurulum

1. Bu klasörü bir GitHub reposu olarak yükleyin.
2. **Settings → Pages**: kaynak olarak `main` dalı, kök klasör. Dosyalar şu adreste yayınlanır:
   `https://<kullanıcı>.github.io/<repo>/data/stations.json`
3. **Actions** sekmesinden *İstasyonları güncelle* iş akışını bir kez elle çalıştırın (`workflow_dispatch`).

Bağımlılık yok; yalnızca Python 3 standart kütüphanesi.

## EPDK servisi hakkında bilinmesi gerekenler

- Uç nokta: `https://apigateway.epdk.gov.tr/sarjIstasyonlari`, kimlik doğrulama yok.
- **GET isteği + JSON gövde** (`{}` = filtresiz) bekler. Gövdesiz GET → 400, POST → 404.
  Tarayıcılar ve Android'deki OkHttp GET'e gövde ekleyemediği için uygulama EPDK'yı **doğrudan çağıramaz**; bu yüzden veri burada üretilip statik dosya olarak sunuluyor.
- Kota çok dar: arka arkaya ikinci istek 429 döner. Script her çalıştırmada tek istek atar, tekrar denemez. 429/5xx durumunda mevcut veri korunur.
- Fiyat alanı **yok**; fiyatlar `prices.json`'dan gelir.
- `sarjIstasyonuIsletmecisi` alanı kişi adı içerebildiği için (KVKK) alınmıyor.

Elle test (kendi bilgisayarınızda):

```bash
python3 scripts/fetch_epdk.py --save-raw raw.json   # bir istek atar, ham yanıtı da saklar
python3 scripts/fetch_epdk.py --from-raw raw.json   # istek atmadan yeniden üretir
python3 scripts/check_prices.py                     # fiyatları doğrular, kapsamı raporlar
python3 scripts/test_fetch_epdk.py
```

## stations.json kaydı

```json
{
  "id": "ŞRJ/1000", "name": "Kerimaba Petrol Arnavutköy",
  "brand": "Zes", "brandKey": "zes",
  "lat": 41.17774, "lng": 28.748019,
  "address": "… No:1292 Arnavutköy / İSTANBUL", "city": "İSTANBUL", "district": "Arnavutköy",
  "green": true,
  "sockets": [{"type": "DC", "standard": "CCS", "kw": 60}],
  "acCount": 0, "acMaxKw": null, "dcCount": 1, "dcMaxKw": 60
}
```

`brandKey`, `prices.json` içindeki `brands` anahtarıyla eşleşir. EPDK'da bir marka farklı yazılırsa `data/brand_aliases.json`'a eşleme ekleyin.

## prices.json ve uygulamada kullanımı

Her marka için `ac` ve `dc` alanı `{min, max}` aralığıdır (tek fiyatlı operatörlerde `min == max`). Birçok büyük operatör (ZES, Trugo, Eşarj, WAT, Otopriz) fiyatı lokasyona göre bir aralık içinde değiştiriyor; tam istasyon fiyatı şu an hiçbir açık kaynakta yok.

Uygulama için öneri:
- Sıralamada **`max`** (garanti üst sınır) kullanın, eşitlikte `min`. `min`'e göre sıralamak yanıltır: "9,73–13,90" gibi aralıklı bir operatör, istasyonlarının çoğunda üst fiyatı alsa bile hep en üste çıkar. Aralığı ekranda "9,73–13,90" olarak gösterin.
- `variesByLocation: true` ise "Kesin fiyat operatör uygulamasında" uyarısı gösterin.
- Markası `prices.json`'da olmayan istasyonları listede tutun ama "fiyat bilinmiyor" olarak en sona koyun; asla tahmini fiyat göstermeyin.
- `confidence: low` olanları küçük bir işaretle belirtin.

Durum (22.10.2026): 13.125 istasyonun **%65,5**'inin fiyatı biliniyor; **%40,7**'si operatörün resmi sayfasından aynı gün doğrulandı. Fiyatı eksik en büyük markalar: Ovolt, Zeplin, K-Şarj, AOS Technology, MKS Şarj.

Fiyat güncellerken: rakamı değiştirin, `checkedAt` ve gerekirse `source`/`confidence` alanını güncelleyin, `updatedAt`'i değiştirin. `check_prices.py` 45 günden eski kontrolleri uyarı olarak listeler.

## Sonraki adımlar

- Fiyatı otomatik kontrol: resmi fiyat sayfası olan operatörler için haftalık değişiklik uyarısı.
- İstasyon bazlı istisnalar (Eşarj, WAT, En Yakıt indirimli istasyon listeleri) için `overrides`.
- Fiyatı eksik markalar.
