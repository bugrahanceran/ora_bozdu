# ora_bozdu

ora_bozdu, mekanların yalnızca bugün iyi veya kötü olup olmadığını değil, zaman
içinde **Bozdu** mu yoksa **Coştu** mu olduğunu gösteren snapshot tabanlı bir
webapp’tir. Phase 1, Eryaman’daki 30 restoran/kafe ile local-first
çalışır.

## Nasıl çalışır?

Google Places API geçmiş rating veya review time series sağlamaz. Bu nedenle
her periyodik fetch, API’nin döndürdüğü venue state ve ham JSON response’larını
timestamp ile SQLite’a append-only yazar. Başlangıç cadence’i haftalıktır;
rating trajectory ve review velocity gibi zaman serileri snapshot’lar
biriktikçe oluşur.

İzlenecek mekanlar elle yazılmaz. `app.discover`, Places API (New) Text Search
ile Eryaman’daki cafe/restoran adaylarını tek genel sorguyla toplar; local
filtre (durum + minimum review sayısı) ve freshness kontrolüyle deterministik
seçim yapar. Aynı markanın tüm şubeleri (ör. 5 Starbucks varsa 5’i de) ayrı
ayrı aday olabilir; şube sayısı sınırlanmaz.

Her venue için Place Details (Legacy) iki kez çağrılır:

- `reviews_sort=most_relevant`
- `reviews_sort=newest`

İki response ayrı ham payload olarak saklanır. Aynı review iki listede de varsa
canonical review tek kez yazılır; hangi sıralamada ve kaçıncı rank’te görüldüğü
ayrı appearance kayıtlarında korunur.

## Tech stack

- Python 3.12+
- FastAPI + Jinja2 + light JavaScript
- SQLite + SQLAlchemy 2 + Alembic
- pydantic-settings + `.env`
- `uv` + `uv.lock`
- pytest, ruff ve pre-commit
- Docker ve Docker Compose

## Local kurulum

`uv` kurulu değilse [resmi uv kurulumunu](https://docs.astral.sh/uv/getting-started/installation/)
kullanın. Ardından:

```bash
cp .env.example .env
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Webapp `http://127.0.0.1:8000` adresinde açılır. Ana sayfa gerçek DB verisinden
30 mekanlık sıralı Bozdu/Coştu skor panosunu; mekan adı, bar konumu, rating,
confidence ve sınıflandırma filtreleriyle gösterir. İlk discovery henüz
çalıştırılmadıysa katalog boştur. Gerçek API kullanan discovery/fetch komutları
öncesinde proje sahibinden açık onay alınır.

Venue detay kartı sade tutulur: barın yanında yalnızca genel `Veri güveni`
gösterilir. Sınıflandırma ve stability pill'leri ile bar altındaki tekrar eden
change-story metni gösterilmez; sinyal açıklamaları ayrı bölümde kalır.

## Configuration

`.env` içindeki temel değerler:

```dotenv
GOOGLE_MAPS_API_KEY=your-key
DATABASE_URL=sqlite:///./data/ora_bozdu.db
VENUE_CATALOG_PATH=config/catalog.yaml
DATA_COLLECTION_CONFIG_PATH=config/data_collection.yaml
SCORING_CONFIG_PATH=config/scoring.v5.toml
```

API key kodda tutulmaz ve `.env` git’e girmez. Google Cloud project’te Places
API (New) Text Search ve Places API Legacy erişimi açık olmalıdır. Legacy
endpoint erişilemezse otomatik fallback yapılmaz.

Mekan hedefi, minimum aday havuzu, cadence, Eryaman çemberi ve filtre eşikleri
(minimum review sayısı dahil) [`config/data_collection.yaml`](config/data_collection.yaml)
dosyasındadır.

## Bir kerelik discovery

Discovery ücretli aşamaları ayrı ayrı sınırlar ve her başarılı sayfayı
`data/discovery-search-cache.json` içine checkpoint eder.

İlk tek-istek smoke:

```bash
uv run python -m app.discover search --max-requests 1 --reset --no-retries
```

Cache durumunu API çağrısı yapmadan görmek için:

```bash
uv run python -m app.discover status
```

İlk sayfa doğrulandıktan ve yeniden onay alındıktan sonra Text Search sayfaları
bounded biçimde alınır. Temel filtreleri geçen benzersiz aday sayısı config'teki
`minimum_candidate_pool` eşiğine ulaşınca kalan page token tüketilmez:

```bash
uv run python -m app.discover search --max-requests 5 --no-retries
```

Search tamamlandığında status çıktısı Legacy freshness için gereken kesin istek
sayısını verir. Bu sayı ayrıca onaylandıktan sonra:

```bash
uv run python -m app.discover freshness --max-requests N --no-retries
```

Task 1'in güncel hedefi 30 venue'dur. Freshness, hedef sayı kadar değil, hard
filtreyi geçen **tüm** eligible adaylar için çalışır (böylece durgun bir aday
daha taze bir yedekle değiştirilebilir); eligible havuz hedef sayıyı ne kadar
aşarsa Legacy istek sayısı da o kadar artar. Freshness response'larının ham
`newest` payload'u cache'te korunur. Aynı tarihli
ilk snapshot fetch'i bu payload'u seed olarak yeniden kullanır ve venue başına
yalnızca eksik `most_relevant` çağrısını yapar. Bu optimizasyon eski, yalnızca
tarih saklayan cache kayıtlarını geriye dönük kurtaramaz.

Freshness tamamlandığında yalnızca local seçim ve katalog yazımı yapılır:

```bash
uv run python -m app.discover finalize
```

Discovery akışı:

1. Cafe ve restoranı birlikte kapsayan tek genel Text Search (New) sorgusu
   yapar; adayın kategorisi Google'ın döndürdüğü `primaryType`'tan gelir.
2. Metromall merkezli config çemberini kapsayan API rectangle'ında sayfaları
   toplar; dönen koordinatlara local radius filtresi uygulayarak gerçek çemberin
   dışındakileri eler. Uygun aday havuzu config eşiğine ulaştığında pagination
   erken tamamlanır.
3. `OPERATIONAL` ve minimum review count (`min_user_ratings_total`) filtrelerini
   local uygular. Aynı markanın şube sayısı sınırlanmaz.
4. Hard filtreyi geçen **her** adayın (yalnızca hedef sayı kadarının değil) en
   yeni yorum tarihini Legacy Details ile kontrol eder; bu, freshness'ın
   gerçekten seçimi değiştirebilmesi (durgun bir adayın daha taze bir yedekle
   yer değiştirebilmesi) için gereklidir.
5. `log(user_ratings_total)` ve gerçek freshness cezasıyla sıralar, tam hedef
   sayıda venue seçer.
6. [`config/catalog.yaml`](config/catalog.yaml) ve
   `reports/discovery-latest.json` üretir.

40 mekana genişleme mevcut kayıtları koruyan yeni bir search cache ile başlar:

```bash
uv run python -m app.discover search --max-requests 1 --target-count 40 --reset --no-retries
```

## Periyodik fetch

Onay öncesi, provider'a hiç çıkmadan ve API key gerektirmeden hangi venue'ların
atlanacağını, hangilerinin freshness cache'inden seed alacağını ve toplam
beklenen HTTP istek sayısını görmek için:

```bash
uv run python -m app.fetch --region eryaman --plan
```

Çıktı hem retry'sız mantıksal istek sayısını (`estimated_http_requests`) hem de
`max_retries` etkinken gerçek üst sınırı (`worst_case_http_requests_with_retries`)
gösterir — retry açıkken (`--no-retries` verilmediğinde) gerçek istek sayısı
mantıksal sayının üzerine çıkabilir. Gerçek koşu:

```bash
uv run python -m app.fetch --region eryaman --no-retries
```

`--no-retries`, canlı koşu öncesinde onaylanan HTTP istek üst sınırının
teknik olarak da aşılmamasını sağlar; retry açık bırakılırsa gerçek istek
sayısı `--plan`'ın gösterdiği worst-case'e kadar çıkabilir. Task 1'de 30 venue
ve iki review sort bulunduğundan ilk tam fetch `--no-retries` ile en fazla 60
Place Details isteği yapar.

İlk canlı kontrolü veya tek mekan retry işlemini katalogdaki `slug` ile
sınırlandırmak mümkündür:

```bash
uv run python -m app.fetch --region eryaman --venue katalog-slug
```

Fetch akışı:

1. YAML venue kataloğunu DB’ye sync eder.
2. Yalnızca katalogda kesin `place_id` taşıyan aktif venue’ları işler.
3. Her venue için `newest` ve `most_relevant` review sıralamalarını alır.
4. İki çağrı da başarılıysa snapshot ve alt kayıtları tek transaction’da yazar.
5. Aynı cadence periodunda mevcut snapshot varsa API çağrısı yapmadan atlar.
6. Aktif Scoring v5 sonuçlarını son snapshot’a kadar yeniden hesaplar.

Bir çağrı başarısız olursa venue için partial snapshot oluşmaz. Diğer venue’lar
işlenmeye devam eder ve CLI non-zero exit code ile hata özetini yazdırır.

Haftalık cron örneği:

```cron
15 4 * * 1 cd /path/to/ora_bozdu && uv run python -m app.fetch --region eryaman
```

`fetch.cadence` config’te `daily` yapıldığında code değişmeden günlük period
idempotency’sine geçilir.

## Scoring v5

Score formülü swappable ve versioned’dır. Aktif ağırlıklar
[`config/scoring.v5.toml`](config/scoring.v5.toml) dosyasındadır:

- Rating trajectory: `%30`
- Review velocity/acceleration: `%20`
- Sentiment + keyword drift: `%20`
- Seviyeyle koşullu stability: `%30`

Structural alanlar (`business_status`, name, `price_level`) score veya
confidence hesabına girmez. `price_level`, keyword drift’i doğrulamak için de
kullanılmaz.

Stability durumları:

- `stable_high`: yüksek seviye + düşük dalgalanma; pozitif “İstikrarlı” ödülü
- `stable_low`: düşük/orta seviye + düşük dalgalanma; nötr/hafif negatif
- `volatile`: dalgalı rating
- `dormant`: rating sayısı da yeni review de uzun süredir artmıyor (bkz. aşağı)
- `insufficient_data`: yeterli snapshot penceresi yok

Eşik, pencere, minimum snapshot ve katkı değerlerinin tamamı config’tedir.
Stability ilk haftalarda unavailable olur ve mevcut sinyal ağırlıkları yeniden
normalize edilir.

**Durgunluk (dormancy) cezası (v5, yeni):** `user_ratings_total` artışı VEYA
yeni review’dan biri hâlâ geliyorsa mekan “fresh” sayılır — sadece review
tarihine bakılmaz. İkisi de durduysa, son aktiviteden bu yana geçen güne göre
kademeli bir ceza uygulanır: `dormancy_grace_days` (60 gün) altında ceza yok;
`dormancy_full_penalty_days`e (365 gün) doğru ceza doğrusal artar ve
`dormancy_penalty_value`e (-1.0) ulaşır. Tam durgunlukta state `dormant`
olur — bu, rating değeri sabit kaldığı için “İstikrarlı” görünen ama aslında
kimsenin artık ilgilenmediği bir mekanı doğru şekilde Bozdu yönüne çeker. Bu
ceza mekanı hiçbir zaman kataloğdan/webapp’ten çıkarmaz, yalnızca skoru
etkiler.

Geçmiş skorları yeniden hesaplamak için:

```bash
uv run python -m app.scoring.recompute --region eryaman --score-version v5
```

## Operasyonel uyarılar

Provider’dan gelen name bir önceki snapshot’tan farklıysa fetch log’una
`venue_name_changed` WARNING yazılır; `business_status` değişirse aynı şekilde
`venue_status_changed` WARNING’i yazılır (ikisi aynı anda değişirse iki ayrı
kayıt oluşur). Önceki/yeni değer fetch özetine eklenir. Bu uyarılar
score/confidence’ı etkilemez ve venue kataloğunu otomatik değiştirmez.

## REST endpoint’leri

- `GET /health`
- `GET /api/venues?q=...`
- `GET /api/venues/{slug}`
- `GET /venues/{slug}`

Webapp canlı Places araması yapmaz; maliyet kontrolü için yalnızca DB içindeki
venue’ları arar.

## Test ve kalite

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run alembic check
```

Testler gerçek API’ye çıkmaz. New Text Search pagination, discovery seçimi
(freshness dahil), Legacy çift-sıralama parse, review deduplication, cadence
idempotency, partial-fetch rollback, operasyonel uyarılar, fetch `--plan`,
Scoring v5 ve web kartı fixture’larla doğrulanır.

## Docker

Web servisi:

```bash
docker compose up --build web
```

Manuel fetch job profile’ı:

```bash
docker compose --profile jobs run --rm fetch
```

Onaylı discovery job:

```bash
docker compose --profile jobs run --rm discover search --max-requests 1 --reset --no-retries
```

Compose discovery servisi `app.discover` entrypoint'ini kullanır; stage ve
argümanlar komut sonuna eklenir.

Servisler aynı `uv.lock` dosyasını kullanır. `.env`, image içine kopyalanmadan
read-only dosya olarak mount edilir. Fetch/web `./data` SQLite volume’unu,
discovery ise host’taki `./config` ve `./reports` dizinlerini kullanır.

## Veri modeli

Ana tablolar:

- `regions`, `venues`
- `fetch_runs`, `fetch_run_warnings`
- `place_snapshots`, `snapshot_payloads`
- `snapshot_reviews`, `snapshot_review_appearances`
- `score_results`

Gelecekteki üçüncü parti review backfill’i `source=backfill` ile eklenebilir;
Task 1’de yalnızca `source=places_api` uygulanır.
