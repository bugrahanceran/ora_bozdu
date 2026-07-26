# Veri Modeli

## Tasarım ilkeleri

- Venue kimliği ile zaman içinde değişen gözlemler ayrılır.
- Cadence-aware snapshot'lar append-only tutulur; cadence `daily`/`weekly`/
  `biweekly` arasında config ile seçilir (Faz 2, 2026-07-25: varsayılan
  `biweekly`, önce `weekly`'ydi).
- API response payload'ları parse edilmiş kolonlara ek olarak ham JSON biçiminde
  saklanır.
- Provider-specific ayrıntılar adapter ve payload katmanında izole edilir.
- SQLite ve PostgreSQL arasında taşınabilir SQLAlchemy tipleri tercih edilir.
- Score sonuçları source snapshot'lardan türetilir; ham verinin yerine geçmez.

## Uygulanan tablolar

### `regions`

Bölge kataloğu. DB'de şu an yalnızca `eryaman` var (tek `Region` kaydı,
`region_id=1`) — ikinci bölge kaydı ancak o bölgenin ilk `app.fetch`/
`sync_catalog` koşusunda oluşur. Faz 2'de ikinci bölge önce Batıkent olarak
planlandı ama hiç gerçek koşu yapılmadan (katalog boşken) 2026-07-25'te
iptal edilip yerine **Armada** (Söğütözü) kondu; Armada da henüz DB'ye
sync edilmedi, ilk onaylı discovery+fetch akışında `Region` kaydı olacak.
`provider_place_id` unique constraint'i `venues` tablosunda global'dır
(bölgeye özel değildir) — bu, aynı gerçek mekanın iki bölgede birden takip
edilmesini DB seviyesinde engeller; asıl koruma discovery'nin
`load_other_region_place_ids` ön-kontrolüdür (bkz. techContext.md Discovery
bölümü), bu constraint son çare güvenlik ağıdır.
`Region`'ın kendisi hiçbir zaman koordinat/geometri taşımadı — bölge merkezi
ve yarıçapı yalnızca `config/data_collection.<slug>.yaml`'da yaşar, DB'ye
hiç yazılmaz.

Temel alanlar: `id`, `slug`, `name`, `created_at`.

### `venues`

Mekanın zaman içinde sabit kalan yerel kimliği ve provider bağlantısı.

Temel alanlar: `id`, `region_id`, `slug`, `display_name`, `provider`,
`provider_place_id`, `is_active`, `is_tracked`, `created_at`.

`provider + provider_place_id` unique olur. Venue listesi discovery tarafından
üretilen bölgeye özel `config/catalog.<slug>.yaml` dosyasından yüklenir;
katalogdaki her aktif venue kesin bir `place_id` taşır. Faz 2'de discovery
hard filtreyi geçen **her** eligible adayı ekler (sabit bir hedef sayı/`--target-count`
kavramı kaldırıldı) ve mevcut venue'yu asla otomatik çıkarmaz. Webapp yalnızca
DB kayıtlarında arama yapar.

`is_tracked` (`0004_add_venue_is_tracked`, `default=true`, 2026-07-25),
`is_active`'le aynı iki-katmanlı (katalog → DB, `sync_catalog` üzerinden)
desende ama farklı bir anlam taşır: `is_active=false` venue'nun kataloktan
kaldırıldığını, `is_tracked=false` ise venue'nun kataloğda kalmaya devam
ettiğini ama şu an periyodik fetch'in **dışında** olduğunu (en popüler
`tracked_venue_limit` kadarına giremediğini) belirtir. `app.fetch` yalnızca
`is_active=true AND is_tracked=true` venue'ları işler. Değer, kataloğun
`VenueCatalogEntry.tracked` alanından gelir ve her aylık `finalize`
koşusunda `rank_tracked_venues` tarafından yeniden hesaplanır (bkz.
techContext.md "Takip edilen mekan" bölümü) — sabit değildir.

### `fetch_runs`

Manuel veya gelecekte scheduled olarak başlatılan fetch işleminin üst kaydı.

Temel alanlar: `id`, `region_id`, `provider`, `cadence`, `period_start`,
`started_at`, `finished_at`, `status`, `requested_count`, `succeeded_count`,
`skipped_count`, `failed_count`, `warning_count`, `error_summary`,
`warning_summary`.

### `fetch_run_warnings`

Fetch sırasında tespit edilen, snapshot yazımını engellemeyen yapılandırılmış
operational warning kayıtlarıdır.

Temel alanlar: `id`, `fetch_run_id`, `venue_id`, `snapshot_id`, `warning_code`,
`details`, `created_at`.

Task 1'de `venue_name_changed` ve `venue_status_changed` warning kodları
kullanılır. `details` içinde ilgili alanın önceki ve yeni değeri bulunur. Aynı
snapshot'ta hem name hem `business_status` değişirse iki ayrı warning kaydı
oluşur. Warning yalnızca log ve fetch özetinde gösterilir; score/confidence
hesabını veya venue kataloğunu değiştirmez. Venue kataloğundan çıkarma ya da
yeni venue açma kararı manuel verilir.

### `place_snapshots`

Bir venue'nun belirli bir cadence periodundaki logical state kaydı.

Temel alanlar: `id`, `venue_id`, `fetch_run_id`, `snapshot_date`, `cadence`,
`period_start`, `captured_at`, `rating`, `user_ratings_total`, `price_level`,
`business_status`, provider name ve `created_at`. Adres, koordinat, website,
Google Maps URL ve `types` kolonları `0003_drop_unused_snapshot_fields`
migration'ıyla şemadan kaldırılmıştır; periyodik fetch field mask'i bu
alanları hiçbir zaman istemediği için sürekli boş kalıyorlardı. Field mask
genişlerse yeni bir migration ile geri eklenir.

**İki kaynak (2026-07-25):** snapshot'lar iki yoldan gelebilir. Eski Google Place
Details fetch'i (`FetchRun.provider="places_api"`, tüm alanlar dolu) **supersede
edildi**; biweekly snapshot artık **Apify**'dan üretilir
(`FetchRun.provider="apify"`, `app.backfill`'deki `persist_snapshots`):
`rating`←`totalScore`, `user_ratings_total`←`reviewsCount`, provider name←`title`.
Apify reviews çıktısında `business_status`/`price_level` olmadığından bu iki alan
Apify snapshot'larında `NULL`'dur (business_status kaybını dormancy sinyali
karşılar, price_level skorda kullanılmıyor). Apify snapshot'larına
`snapshot_payloads`/`snapshot_reviews` yazılmaz — review'lar ayrı `venue_reviews`
corpus'una gider, scoring absolute agregatı `place_snapshots`'tan okur.

`venue_id + cadence + period_start` unique constraint cadence-aware idempotency
sağlar. `snapshot_payloads` içindeki request-variant unique constraint ile
birlikte aynı period + venue + review sort duplicate olamaz. Snapshot ve alt
kayıtları, config'te zorunlu tüm review-sort response'ları alındıktan sonra
venue bazında tek transaction ile yazılır (Faz 2, 2026-07-25: aktif config
tek sort — `newest` — ister; adapter genel olarak birden fazlasını
destekler). Aynı period içindeki ikinci çalıştırma mevcut başarılı
snapshot'ı atlar; başarısız venue için yarım snapshot olmadığı için güvenli retry
yapılır.

### `snapshot_payloads`

API response'un değiştirilmeden saklanan ham JSON kaydıdır. Aynı logical
snapshot için birden fazla request variant bulunabilir.

Temel alanlar: `id`, `snapshot_id`, `provider`, `request_variant`,
`review_sort`, `fetched_at`, `raw_payload`, `payload_hash`.

Places Legacy adapter'ı `review_sort` değeri olarak `most_relevant` ve/veya
`newest` üretebilir; aktif `FetchConfig.review_sorts` Faz 2'de (2026-07-25)
yalnızca `newest` ister, dolayısıyla yeni snapshot'lar tek `review_sort`
kaydıyla oluşur (geçmiş snapshot'larda ikisi de görülebilir).
`snapshot_id + provider + request_variant` unique olur.

### `snapshot_reviews`

Logical snapshot içinde deduplicate edilmiş, parse edilmiş canonical review
kaydıdır.

Temel alanlar: `id`, `snapshot_id`, `source`, `provider_review_id`,
`dedup_key`, `author_name`, `author_url`, `published_at`, `rating`, `text`,
`language`, `original_language`, `translated`, `raw_review`.

Task 1'de `source=places_api` kullanılır. Gelecekte `source=backfill` kabul
edilir. `snapshot_id + dedup_key` unique olur.

Provider review ID sağlamıyorsa `dedup_key`; venue provider kimliği, normalize
edilmiş author kimliği/adı, review timestamp'i, rating ve normalize edilmiş
orijinal metnin SHA-256 hash'i ile deterministik üretilir. Hash'e girmeden önce
Unicode ve whitespace normalization uygulanır. Bu yaklaşım aynı review'un iki
sıralamada tekrar etmesini birleştirir.

### `snapshot_review_appearances`

Bir canonical review'un hangi request sıralamasında ve kaçıncı sırada geldiğini
korur.

Temel alanlar: `id`, `snapshot_review_id`, `review_sort`, `rank`,
`snapshot_payload_id`.

`snapshot_review_id + review_sort` unique olur. Aynı review hem
`most_relevant` hem `newest` içinde bulunursa iki appearance kaydı oluşur;
review metni yalnızca bir kez tutulur. Aktif config tek sort istediğinden
(2026-07-25) yeni snapshot'larda bu yalnızca tek appearance ile sonuçlanır;
mekanizma değişmedi, girdi çeşitliliği azaldı.

### `venue_reviews`

Apify Google Maps Reviews Scraper actor'ünden gelen, **venue'ya bağlı** tarihsel
review corpus'u (`snapshot_reviews`'un aksine bir fetch snapshot'ına değil
doğrudan venue'ya bağlı). `0005_add_venue_reviews` (2026-07-25) ile eklendi.

Temel alanlar: `id`, `venue_id`, `source` (default `backfill`),
`provider_review_id`, `dedup_key`, `author_name`, `published_at`, `rating`
(1-5), `text`, `language`, `sub_ratings` (JSON, kategori-bazlı puanlar —
sağlayıcı veriyorsa), `scraped_at`. `venue_id + dedup_key` unique (idempotent
import). `dedup_key` Apify'ın stabil `reviewId`'sinden (varsa) türetilir;
yoksa `make_review_key` ile içerik-hash'i. Import Apify'ın düz review-item
listesini alır ve her item'ın `placeId`'sini (Google `ChIJ...`) doğrudan
`Venue.provider_place_id`'ye join eder (bkz. techContext.md "Review backfill").

Scoring bir venue'nun `venue_reviews` corpus'u varsa review-tabanlı sinyalleri
(sentiment, v6 count-split rating trajesi, review-consistency stability)
`snapshot_reviews` yerine bundan besler (corpus daha zengin ve tarih-tutarlı);
corpus yoksa `snapshot_reviews` fallback. `SnapshotReview` ve `VenueReview` ortak `ReviewInput` protokolünü
(dedup_key/published_at/rating/text) sağladığından engine ikisini de tüketebilir.
Mutlak seviye (agregat rating, toplam sayı) hâlâ `place_snapshots`'tan (Places
API ground-truth) gelir; Apify yalnızca trend/geçmiş/sentiment verir.

### `score_results`

Versioned scoring çıktısıdır ve yeniden üretilebilir.

Temel alanlar: `id`, `venue_id`, `as_of_snapshot_id`, `score_version`,
`change_score`, `confidence`, `classification`, `stability_state`,
`signal_breakdown`, `change_story`, `computed_at`.

`venue_id + as_of_snapshot_id + score_version` unique olur. `recompute`, aynı
version için upsert veya açık bir replace stratejisiyle deterministic çalışır;
ham snapshot'ları değiştirmez.

`business_status`, name ve `price_level` snapshot'ta saklanmaya devam eder ama
`score_results` üretiminde kullanılmaz. Name değişikliği yalnızca
`fetch_run_warnings` üzerinden operasyonel olarak izlenir.

## Backfill hazırlığı

Task 1 üçüncü parti backfill yapmaz. İleride son 6 aya ait review'lar geldiğinde:

- `source=backfill` ile kaynak ayrımı korunur.
- Provider review ID varsa öncelikli dedup anahtarı olur.
- Cross-provider eşleştirme ayrı bir normalization/dedup servisi olarak ele
  alınır; Places verisi otomatik olarak üzerine yazılmaz.
- Review'un kendi `published_at` değeri event time, ingest zamanı ise ayrı
  `captured_at`/run zamanı olarak korunur.

## Schema değişiklik geçmişi

- **2026-07-25 — `0005_add_venue_reviews`:** `venue_reviews` tablosu eklendi
  (Apify'dan gelen tarihsel review corpus'u, `source=backfill`,
  `venue_id + dedup_key` unique — bkz. yukarıdaki `venue_reviews` bölümü ve
  techContext.md "Review backfill + Scoring v6" bölümü). Scratch DB'de
  upgrade→downgrade→upgrade→`alembic check` temiz. Şemayla birlikte gelen
  davranış: aktif scoring version `scoring.v6.toml`'a yükseltildi (v5 frozen);
  v6, corpus varsa `rating_trajectory`'yi count-split (newest yarı vs older yarı)
  ve `stability`'yi review-consistency ile hesaplıyor (score girdisi değişikliği
  → yeni version; bkz. 2026-07-26 kaydı).
- **2026-07-25 — `0004_add_venue_is_tracked`:** `venues.is_tracked`
  (`Boolean`, `default=true`) eklendi — dinamik top-N "takip edilen mekan"
  seçimi için (bkz. yukarıdaki `venues` bölümü ve techContext.md "Takip
  edilen mekan" bölümü). Upgrade/downgrade/upgrade + `alembic check`
  önce scratch DB'de, sonra kullanıcı onayıyla gerçek `data/ora_bozdu.db`'de
  (yedek alınarak) doğrulandı — ikisi de temiz. Şemayla birlikte gelen
  davranış değişiklikleri: `fetch.cadence` varsayılanı `weekly`'den
  `biweekly`'e düştü (yeni `cadence_anchor_date` alanına hizalı;
  `place_snapshots`/`fetch_runs`'ın `cadence`/`period_start` kolonları
  zaten string/date olduğundan bu şema değişikliği gerektirmedi) ve
  `FetchConfig.review_sorts` artık yalnızca `newest` kabul ediyor (adapter
  hâlâ genel çoklu-sort'u destekler, yalnızca aktif config daraltıldı).
- **2026-07-24 — Faz 2 discovery genişletmesi (Eryaman + Batıkent):** DB
  şeması/migration değişmedi — `Region`/`Venue` zaten bölge geometrisi
  taşımıyordu ve `venues.provider_place_id` unique constraint'i zaten
  global'di, bu yüzden bu ikinci bölge için hazır bir backstop olarak
  kullanıldı. `batikent` ikinci `Region` kaydı olarak eklendi. Bölgeler
  arası koruma (aynı `place_id`'nin iki bölgede birden takip edilmemesi)
  DB seviyesinde değil, discovery'nin `load_other_region_place_ids`
  ön-kontrolüyle (dosya seviyesinde, `catalog.*.yaml` glob'u) sağlanıyor;
  DB constraint'i yalnızca bu ön-kontrol bir şekilde atlanırsa devreye giren
  son çare güvenlik ağı. Discovery mekanizması Text Search'ten Nearby
  Search + grid'e taşındı ve "en iyi N'i seç" yerine "hard filtreyi geçen
  herkesi al" semantiğine geçti (bkz. techContext.md Discovery bölümü) —
  bu tamamen config/kod katmanında bir değişiklik, hiçbir DB tablosunu
  etkilemedi.
- **2026-07-24 — Scoring v5 (dormancy):** Şema değişmedi (`score_results.
  signal_breakdown` zaten serbest JSON). `stability` sinyaline "durgunluk"
  kavramı eklendi: `user_ratings_total` artışı VEYA yeni review varsa mekan
  fresh sayılır; ikisi de durduysa, son aktiviteden bu yana geçen güne göre
  kademeli bir ceza uygulanır (60 gün altı ceza yok, 365 günde tam ceza
  `-1.0`) ve tam eşikte state `dormant` olur. Bu asla venue'yu kataloğdan
  çıkarmaz, yalnızca `change_score`'u etkiler. `StabilityConfig`'e 3 yeni alan
  (`dormancy_grace_days`, `dormancy_full_penalty_days`,
  `dormancy_penalty_value`) eklendi; eski `scoring.v4.toml` bunları
  içermediği için nötr default'larla (etkisiz) yüklenmeye devam eder.
  `app/config.py` ve gerçek `.env`'deki `SCORING_CONFIG_PATH`, `scoring.v5.
  toml`'a güncellendi.
- **2026-07-24 — `0003_drop_unused_snapshot_fields`:** `place_snapshots`
  tablosundan hiç doldurulmayan `formatted_address`, `latitude`, `longitude`,
  `types`, `website`, `google_maps_url` kolonları kaldırıldı (upgrade/downgrade
  doğrulandı). Bununla birlikte `PlaceState`/Legacy adapter parse'ı ve venue
  detay kartındaki Google Maps linki de kaldırıldı; minimal field mask
  ilkesiyle uyumlu hale getirildi.
- **2026-07-19 — Freshness raw-cache sidecar:** DB şeması değişmeden discovery
  cache'e ham `details_newest` payload, fetched timestamp ve payload hash
  eklendi. Aynı tarihli ilk fetch bu payload'u yeniden kullanabilir; snapshot
  yine iki sort payload'u birlikte hazır olduğunda atomik yazılır.
- **2026-07-18 — `0001_initial_schema`:** Aşağıdaki logical model ilk Alembic
  migration olarak SQLite üzerinde upgrade/downgrade ile doğrulandı.
- **2026-07-18 — Başlangıç tasarımı:** Günlük append-only snapshot,
  çift-sıralama raw payload, snapshot içi review deduplication, provider/source
  ayrımı ve versioned score sonucu kararlaştırıldı.
- **2026-07-18 — Scoring v2:** Seviyeyle koşullu stability beşinci sinyal olarak
  eklendi. Nihai bar değeri `change_score` olarak adlandırıldı ve
  `stability_state` kalıcı score çıktısına eklendi.
- **2026-07-18 — Scoring v3:** Structural changes score signal'ı tamamen
  çıkarıldı. Ağırlığı review velocity/acceleration ve stability'ye eşit
  dağıtıldı. Name değişimi score dışı `venue_name_changed` operational warning
  olarak tasarlandı; `price_level` ile keyword drift bağlantısı kaldırıldı.
- **2026-07-19 — Scoring v4:** Stability'nin ürün önemi artırıldı. Ağırlığı
  `0.25`ten `0.30`a çıkarılırken review velocity/acceleration `0.25`ten `0.20`ye
  indirildi; diğer iki sinyal `0.30` ve `0.20` olarak korundu. Sinyal bazındaki
  `reliability` UI'da `Kanıt gücü` olarak adlandırıldı.
- **2026-07-18 — Discovery/fetch nihai kararı:** Katalog üretimi Places API
  (New) Text Search + Legacy newest freshness kontrolüne taşındı. Periyodik
  fetch yalnızca YAML katalogdaki `place_id` kayıtlarını işler. Cadence haftalık
  oldu; idempotency `venue + cadence + period_start` olarak tasarlandı.
- **2026-07-18 — `0002_cadence_periods`:** `fetch_runs` ve `place_snapshots`
  tablolarına `cadence`/`period_start` eklendi; snapshot unique constraint'i
  cadence perioduna taşındı. Fetch'in discovery yapmamasını garanti etmek için
  eski `venues.seed_query` alanı kaldırıldı.
