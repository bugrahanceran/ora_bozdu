# ora_bozdu

ora_bozdu, mekanların yalnızca bugün iyi veya kötü olup olmadığını değil, zaman
içinde **Bozdu** mu yoksa **Coştu** mu olduğunu gösteren snapshot tabanlı bir
webapp’tir. Faz 1, Eryaman’da 30 restoran/kafe ile local-first çalıştı. Faz 2,
Eryaman ve Batıkent’te kategori bazlı (yalnızca "restoran"/"kafe" değil, Google
Places API’nin tüm "Food and Drink" tip kümesi) neredeyse eksiksiz bir mekan
envanteri hedefler; iki bölge ayrı `Region` kayıtları ve ayrı config
dosyalarıyla yönetilir.

## Nasıl çalışır?

Google Places API geçmiş rating veya review time series sağlamaz. Bu nedenle
her periyodik fetch, API’nin döndürdüğü venue state ve ham JSON response’larını
timestamp ile SQLite’a append-only yazar. Fetch cadence’i iki haftada birdir
(`fetch.cadence: biweekly`, periyot sınırları `cadence_anchor_date`'e göre
hizalanır); rating trajectory ve review velocity gibi zaman serileri
snapshot’lar biriktikçe oluşur.

İzlenecek mekanlar elle yazılmaz. `app.discover`, her bölgenin dairesel arama
alanını küçük hücrelere bölüp (grid) Places API (New) Nearby Search ile her
hücreyi tip bazlı (restoran, kafe, pastane, dondurmacı vb. — Google'ın "Food
and Drink" tip kümesinin tamamı) tarar; local filtre (durum + minimum review
sayısı + bölge yarıçapı) uygulanır ve hard filtreyi geçen **herkes** kataloğa
eklenir — bir "en iyi N'i seç" kırpması yoktur. Aynı markanın tüm şubeleri
(ör. 5 Starbucks varsa 5’i de) ayrı ayrı aday olur; şube sayısı sınırlanmaz.
Kataloğa eklenmek periyodik fetch'e girmekle aynı şey değildir — bkz. aşağıdaki
"Takip edilen mekan (tracked) seçimi".

Her venue için Place Details (Legacy) `reviews_sort=newest` ile çağrılır ve
response'taki `rating`/`user_ratings_total`/`price_level`/`business_status`
alanları (bunlar `fields` parametresiyle gelir, sort'tan bağımsızdır) state
olarak, `reviews` alanı da review listesi olarak kaydedilir. Adapter genel
olarak birden fazla `reviews_sort`'u aynı anda destekler (her sort ayrı ham
payload olur; aynı review birden fazla listede görülürse canonical review tek
kez yazılır, hangi sıralamada ve kaçıncı rank'te göründüğü ayrı appearance
kayıtlarında korunur) — ama aktif config yalnızca `newest` ister.
`most_relevant`'ın döndürdüğü review kümesi Google tarafından kontrolsüz
olduğundan (tarih/sıra garantisi yok) scoring'e güvenilir bir katkısı yoktur;
`newest` + review sayısı artışı zaten `rating_trajectory`, `review_velocity` ve
`stability`'nin (dormancy dahil) ihtiyaç duyduğu her şeyi karşılar.

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

Webapp `http://127.0.0.1:8000` adresinde açılır. Ana sayfa gerçek DB
verisinden sıralı Bozdu/Coştu skor panosunu; mekan adı, bar konumu, rating,
confidence ve sınıflandırma filtreleriyle gösterir (venue sayısı katalog
büyüklüğüyle birlikte değişir, sabit değildir). İlk discovery henüz
çalıştırılmadıysa katalog boştur. Gerçek API kullanan discovery/fetch komutları
öncesinde proje sahibinden açık onay alınır.

Venue detay kartı sade tutulur: barın yanında yalnızca genel `Veri güveni`
gösterilir. Sınıflandırma ve stability pill'leri ile bar altındaki tekrar eden
change-story metni gösterilmez; sinyal açıklamaları ayrı bölümde kalır.

## Configuration

`.env` içindeki temel değerler (varsayılan olarak Eryaman'ı gösterir):

```dotenv
GOOGLE_MAPS_API_KEY=your-key
DATABASE_URL=sqlite:///./data/ora_bozdu.db
VENUE_CATALOG_PATH=config/catalog.eryaman.yaml
DATA_COLLECTION_CONFIG_PATH=config/data_collection.eryaman.yaml
SCORING_CONFIG_PATH=config/scoring.v5.toml
```

API key kodda tutulmaz ve `.env` git’e girmez. Google Cloud project’te Places
API (New) Nearby Search ve Places API Legacy erişimi açık olmalıdır. Legacy
endpoint erişilemezse otomatik fallback yapılmaz.

Her bölgenin kendi config/katalog/cache dosyası vardır:

| Bölge | Config | Katalog | Search cache |
| --- | --- | --- | --- |
| Eryaman | [`config/data_collection.eryaman.yaml`](config/data_collection.eryaman.yaml) | [`config/catalog.eryaman.yaml`](config/catalog.eryaman.yaml) | `data/discovery-search-cache.eryaman.json` |
| Batıkent | [`config/data_collection.batikent.yaml`](config/data_collection.batikent.yaml) | [`config/catalog.batikent.yaml`](config/catalog.batikent.yaml) | `data/discovery-search-cache.batikent.json` |

`app.discover` ve `app.fetch` CLI'ları `--data-collection-config` ve
`--catalog` bayraklarıyla bu dosyalardan hangisinin kullanılacağını seçer
(varsayılan `.env`'deki değerdir, yani Eryaman). Her config dosyasında bölge
merkezi, arama yarıçapı (`radius_meters`), grid hücre yarıçapı
(`cell_radius_meters`), aranacak Places tipleri (`included_types`) ve minimum
review sayısı (`min_user_ratings_total`) bulunur. Yeni bir bölge eklemek için
her iki dosyayı da kopyalayıp merkez koordinatını değiştirmek ve boş bir
katalog dosyası (`venues: []`) oluşturmak yeterlidir — code değişikliği
gerekmez.

## Bir kerelik discovery

Her bölgenin dairesel arama alanı (`radius_meters`), örtüşen küçük dairelere
(`cell_radius_meters`) bölünür — bir "hücre" aslında **hücre × tip-grubu**
kombinasyonudur, çünkü Nearby Search `includedTypes` başına en fazla 50 tip
kabul eder ve tam Food & Drink kapsamı ~150 tip içerir (config'teki
`included_types` otomatik olarak ≤50'lik gruplara bölünür). Discovery, ücretli
aşamaları ayrı ayrı sınırlar ve her başarılı hücre çağrısını cache dosyasına
checkpoint eder.

Sıfır maliyetli deneme (API çağrısı yapmaz, sadece grid'i hesaplayıp hücre
sayısını gösterir — `cell_radius_meters`/`radius_meters`'ı ayarlamak için
tekrar tekrar çalıştırılabilir):

```bash
uv run python -m app.discover search --max-requests 0 --reset \
  --data-collection-config config/data_collection.eryaman.yaml \
  --catalog config/catalog.eryaman.yaml
```

İlk tek-istek smoke (onay sonrası):

```bash
uv run python -m app.discover search --max-requests 1 --no-retries \
  --data-collection-config config/data_collection.eryaman.yaml \
  --catalog config/catalog.eryaman.yaml
```

Cache durumunu API çağrısı yapmadan görmek için `status`, tüm hücreler
bitene kadar bounded artışlarla devam etmek için tekrar `search` kullanılır
(argümanlar aynı `--data-collection-config`/`--catalog` çiftiyle):

```bash
uv run python -m app.discover status --data-collection-config config/data_collection.eryaman.yaml --catalog config/catalog.eryaman.yaml
uv run python -m app.discover search --max-requests 20 --no-retries --data-collection-config config/data_collection.eryaman.yaml --catalog config/catalog.eryaman.yaml
```

Bir hücre tam `max_result_count` (20) sonuç döndürürse (kırpılma ihtimali,
o hücrede daha fazla mekan olabilir ama Nearby Search'te sayfalama yok), bu
hücre `cells_flagged_for_review` sayısına eklenir ve sonuç olduğu gibi kabul
edilir — **otomatik bölünme yapılmaz** (2026-07-24'te kaldırıldı: ilk canlı
Eryaman koşusunda hücrelerin ~%16'sı tavana çarpıp toplam istek sayısını
276'dan 456'ya çıkarmıştı; öngörülebilir/sabit istek sayısı önceliğiyle
kaldırıldı — bkz. aşağıdaki not). Böylece bir bölgenin toplam arama isteği
sayısı her zaman tam olarak `hücre × tip-grubu` kadardır, dry-run'da görülen
sayı kesinleşir.

Arama tamamlandığında status çıktısı Legacy freshness için gereken kesin
istek sayısını verir (hard filtreyi geçen **her** aday için — bir "hedef
sayı" kırpması olmadığından herkes freshness kontrolünden geçer). Bu sayı
ayrıca onaylandıktan sonra:

```bash
uv run python -m app.discover freshness --max-requests N --no-retries --data-collection-config config/data_collection.eryaman.yaml --catalog config/catalog.eryaman.yaml
```

Freshness response'larının ham `newest` payload'u cache'te korunur, ama bu
payload yalnızca `fields=reviews` ile alındığından (`name` içermez) fetch
tarafından state seed'i olarak **yeniden kullanılamaz** — venue başına ilk
snapshot her zaman kendi tam-alanlı `newest` çağrısını yapar. Bu, tek-sort
rejiminin bilinçli bir basitleştirmesidir: seed reuse yalnızca ikinci bir sort
(`most_relevant`) olduğunda gerçek bir HTTP tasarrufu sağlıyordu.

Freshness tamamlandığında yalnızca local seçim ve katalog yazımı yapılır:

```bash
uv run python -m app.discover finalize --data-collection-config config/data_collection.eryaman.yaml --catalog config/catalog.eryaman.yaml
```

Discovery akışı:

1. Bölge çemberini `cell_radius_meters` boyutunda karesel bir grid ile
   kaplar (her hücrenin çevrel dairesi Nearby Search'e gönderilir); tip
   listesi 50'lik gruplara bölünür, her coğrafi hücre her grup için ayrı
   taranır.
2. Bir hücre tavana (`max_result_count`) çarparsa sonuç olduğu gibi kabul
   edilir ve rapora "incelemeye açık" olarak işaretlenir — otomatik bölünme
   yoktur, istek sayısı böylece her zaman öngörülebilir kalır.
3. `OPERATIONAL`, minimum review count (`min_user_ratings_total`), bölge
   yarıçapı (kenar hücrelerin taşması olası, bu yüzden gerçek mesafe ayrıca
   kontrol edilir) ve `excluded_primary_types` (config'te listelenen, yemekle
   ilgisiz kategoriler — bkz. aşağıdaki not) filtrelerini local uygular. Aynı
   markanın şube sayısı sınırlanmaz. Zaten başka bir bölgede takip edilen bir
   `place_id` de burada elenir (bkz. aşağıdaki "bölgeler arası koruma").
4. Hard filtreyi geçen **her** adayın en yeni yorum tarihini Legacy Details
   ile kontrol eder.
5. Filtreyi geçen ve freshness'ı bilinen **her** adayı kataloğa ekler — bir
   "en iyi N'i seç" kırpması yoktur; `score_candidate` yalnızca insan-okur
   rapordaki sıralama içindir.
6. Kataloğun tamamını (eski + yeni) `user_ratings_total`'a göre yeniden
   sıralar ve en popüler `tracked_venue_limit` kadarını `tracked` işaretler
   (bkz. aşağıdaki "Takip edilen mekan (tracked) seçimi").
7. [`config/catalog.<bölge>.yaml`](config/catalog.eryaman.yaml) ve
   `reports/discovery-latest.<bölge>.json` üretir.

**Takip edilen mekan (tracked) seçimi (2026-07-25 eklendi):** Kataloğa
eklenmek periyodik fetch'e girmek için yeterli değildir. `finalize`, her
bölgenin **tüm** kataloğunu (bu turda taranan güncel review sayılarıyla,
taranmayanlar için son bilinen review sayısıyla) `user_ratings_total`'a göre
azalan sıralar; en popüler `tracked_venue_limit` (varsayılan `200`) kadarı
`tracked: true`, kalanı `tracked: false` olur — silinmez, kataloğda kalır ve
raporda "yeterli review sayısına ulaşamadı" durumundadır. `app.fetch` yalnızca
`tracked: true` venue'ları işler (hem katalog hem DB `Venue.is_tracked`
kolonu üzerinden çift katmanlı, `active`/`is_active` ile aynı desen). Bu
**sabit bir seçim değildir**: her `finalize` koşusunda yeniden hesaplanır, bu
yüzden review sayısı artan bir mekan sonraki bir döngüde tekrar top-N'e
girebilir. Hiç review verisi olmayan (ne bu turda taranmış ne daha önce
bilinen) mekanlar mevcut `tracked` durumunda dokunulmadan bırakılır. Yeni
keşfedilen mekanlara özel bir koruma/grace-period yoktur — Google Places API
açılış tarihi vermediğinden güvenilir bir "ne kadar yeni" sinyali yok; düşük
review sayısıyla başlayan bir mekan organik olarak review biriktirdikçe
doğal yoldan yükselir.

**Bölgeler arası koruma:** aynı gerçek mekanın iki bölgede birden takip
edilmesini önlemek için, `catalog.<bölge>.yaml` dosyalarının hepsi
(`config/catalog.*.yaml` glob'u ile) taranır ve diğer bölgelerde zaten
kayıtlı `place_id`'ler hem freshness kontrolünden hem finalize'dan hariç
tutulur (DB'deki global `uq_venue_provider_place_id` constraint'i son çare
güvenlik ağıdır). Eryaman ve Batıkent merkezleri ~7.8km ayrık olduğundan
(sırasıyla ~3km yarıçaplı çemberlerle) bu çakışma normal koşulda
beklenmez.

**Yeni bir bölge eklerken:** ilk `search --reset` öncesi elle boş bir katalog
dosyası oluşturulmalıdır (`config/catalog.batikent.yaml` zaten bu şekilde,
`venues: []` ile, hazır bulunuyor) — `load_catalog` dosya yoksa hata verir.

**`excluded_primary_types` (2026-07-24 eklendi):** Nearby Search'ün
`includedTypes`'ı bir mekanın TÜM tip etiketlerine bakar (yalnızca
`primaryType`'a değil) — bu yüzden kuaför, market, klinik gibi yemekle
ilgisiz mekanlar da ikincil bir food-tipi etiketi yüzünden sonuçlara
sızabiliyor. Bunlar Google'ın atadığı `primaryType`'a göre local olarak
elenir; `config/data_collection.*.yaml`'daki liste, gerçek Eryaman
koşusunda bulunan somut örneklere (kuaför, berber, market, klinik, havuz,
oyun evi, simülasyon merkezi vb.) dayanır. Eleme, freshness'tan **önce**
olur — bu mekanlar için gereksiz Legacy Place Details isteği atılmaz.

## Periyodik fetch

Onay öncesi, provider'a hiç çıkmadan ve API key gerektirmeden hangi venue'ların
atlanacağını, hangilerinin freshness cache'inden seed alacağını ve toplam
beklenen HTTP istek sayısını görmek için:

```bash
uv run python -m app.fetch --region eryaman --plan
uv run python -m app.fetch --region batikent --plan --data-collection-config config/data_collection.batikent.yaml --catalog config/catalog.batikent.yaml
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
sayısı `--plan`'ın gösterdiği worst-case'e kadar çıkabilir. Her venue tek
review sort (`newest`) gerektirdiğinden ve yalnızca `tracked: true`
venue'lar işlendiğinden, ilk tam fetch `--no-retries` ile en fazla
`1 × takip edilen (tracked) venue sayısı` Place Details isteği yapar (Eryaman
için `tracked_venue_limit=200` ile üst sınır 200'dür) — `--plan` çıktısındaki
`estimated_http_requests` gerçek sayıyı verir; bir bölgeye özel config
kullanılıyorsa `--data-collection-config` bayrağı ile birlikte
çalıştırılmalıdır.

İlk canlı kontrolü veya tek mekan retry işlemini katalogdaki `slug` ile
sınırlandırmak mümkündür:

```bash
uv run python -m app.fetch --region eryaman --venue katalog-slug
```

Fetch akışı:

1. YAML venue kataloğunu DB’ye sync eder (`is_active` ve `is_tracked` dahil).
2. Yalnızca katalogda kesin `place_id` taşıyan, aktif **ve** takip edilen
   (`tracked: true`) venue’ları işler.
3. Her venue için `newest` review sıralamasını alır.
4. Çağrı başarılıysa snapshot ve alt kayıtları tek transaction’da yazar.
5. Aynı cadence periodunda mevcut snapshot varsa API çağrısı yapmadan atlar.
6. Aktif Scoring v5 sonuçlarını son snapshot’a kadar yeniden hesaplar.

Bir çağrı başarısız olursa venue için partial snapshot oluşmaz. Diğer venue’lar
işlenmeye devam eder ve CLI non-zero exit code ile hata özetini yazdırır.

**Zamanlama (2026-07-25 itibarıyla elle):** `app.discover` (search →
freshness → finalize) ayda bir, `app.fetch` iki haftada bir çalıştırılır;
ikisi de şu an bir scheduler'a bağlı değildir, proje sahibi elle tetikler.
Otomatik zamanlama (ör. bir CI/CD pipeline'ında scheduled job) Faz 4
kapsamında değerlendirilecek — `cron` doğası gereği takvim alanlarıyla
çalışır ve "iki haftada bir" gibi epoch-tabanlı bir periyodu doğrudan ifade
edemez, bu yüzden otomatik hale getirilirse `cadence_anchor_date` ile aynı
parity kontrolü job seviyesinde de ayrıca uygulanmalıdır.

`fetch.cadence` config’te `daily`/`weekly`/`biweekly` arasında
değiştirilebilir; `biweekly` seçiliyken `cadence_anchor_date` zorunludur
(periyot sınırlarının hangi Pazartesi'ye hizalanacağını belirler).

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

Testler gerçek API’ye çıkmaz. Nearby Search grid üretimi, discovery take-all
mantığı (freshness dahil), takip edilen (tracked) mekan seçimi ve yeniden
sıralaması, bölgeler arası koruma, Legacy review sort parse (adapter genel
çoklu-sort'u destekler, aktif config tek `newest` ister), review
deduplication, günlük/haftalık/iki haftalık cadence idempotency,
partial-fetch rollback, operasyonel uyarılar, fetch `--plan`, Scoring v5 ve
web kartı fixture’larla doğrulanır.

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
argümanlar (örn. `--data-collection-config config/data_collection.batikent.yaml
--catalog config/catalog.batikent.yaml`) komut sonuna eklenir. `docker compose
run <servis> <args>` o servisin sabit `command:`'ını **değiştirir**, üzerine
eklemez — `fetch` servisinin varsayılan komutu `alembic upgrade head &&` ile
başladığından, ekstra argümanlarla çalıştırılan bir `run` bu adımı atlar; ilk
Batıkent koşularını (Eryaman'da da yapıldığı gibi) doğrudan `uv run` ile
yapmak daha güvenlidir.

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
