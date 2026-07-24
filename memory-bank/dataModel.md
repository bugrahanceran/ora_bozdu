# Veri Modeli

## Tasarım ilkeleri

- Venue kimliği ile zaman içinde değişen gözlemler ayrılır.
- Cadence-aware snapshot'lar append-only tutulur; başlangıç cadence'i
  haftalıktır ve config ile günlük yapılabilir.
- API response payload'ları parse edilmiş kolonlara ek olarak ham JSON biçiminde
  saklanır.
- Provider-specific ayrıntılar adapter ve payload katmanında izole edilir.
- SQLite ve PostgreSQL arasında taşınabilir SQLAlchemy tipleri tercih edilir.
- Score sonuçları source snapshot'lardan türetilir; ham verinin yerine geçmez.

## Uygulanan tablolar

### `regions`

Bölge kataloğu. Task 1'de `eryaman` kaydı kullanılır.

Temel alanlar: `id`, `slug`, `name`, `created_at`.

### `venues`

Mekanın zaman içinde sabit kalan yerel kimliği ve provider bağlantısı.

Temel alanlar: `id`, `region_id`, `slug`, `display_name`, `provider`,
`provider_place_id`, `is_active`, `created_at`.

`provider + provider_place_id` unique olur. Venue listesi discovery tarafından
üretilen `config/catalog.yaml` dosyasından yüklenir; katalogdaki her aktif venue
kesin bir `place_id` taşır. `--target-count N` mevcut kayıtları koruyarak ekleme
yapar ve mevcut venue'yu otomatik çıkarmaz. Webapp yalnızca DB kayıtlarında
arama yapar.

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

`venue_id + cadence + period_start` unique constraint cadence-aware idempotency
sağlar. `snapshot_payloads` içindeki request-variant unique constraint ile
birlikte aynı hafta/gün + venue + review sort duplicate olamaz. Snapshot ve alt
kayıtları, iki zorunlu API response'u da alındıktan sonra venue bazında tek
transaction ile yazılır. Aynı period içindeki ikinci çalıştırma mevcut başarılı
snapshot'ı atlar; başarısız venue için yarım snapshot olmadığı için güvenli retry
yapılır.

### `snapshot_payloads`

API response'un değiştirilmeden saklanan ham JSON kaydıdır. Aynı logical
snapshot için birden fazla request variant bulunabilir.

Temel alanlar: `id`, `snapshot_id`, `provider`, `request_variant`,
`review_sort`, `fetched_at`, `raw_payload`, `payload_hash`.

Task 1 Places adapter'ı için `review_sort` değerleri `most_relevant` ve `newest`
olur. `snapshot_id + provider + request_variant` unique olur.

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
review metni yalnızca bir kez tutulur.

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
