# Teknik Bağlam

## Tech stack

- Python 3.12+
- FastAPI; REST endpoint'leri ve Jinja2 frontend aynı servis içinde
- Light JavaScript; SPA framework yok
- SQLite + SQLAlchemy ORM
- İlk günden Alembic migration
- `.env` + `pydantic-settings`
- `uv`, `pyproject.toml` ve `uv.lock`; `requirements.txt` yok
- `pytest`, `ruff` ve `pre-commit`
- Local development için venv; parity/testing için Docker ve Docker Compose

## Veri stratejisi

Places API tarihsel rating/review time series sağlamaz. Sistem bu nedenle
snapshot-first tasarlanır:

- Her başarılı periyodik fetch, venue state ve API'den dönen ham payload'ları
  timestamp ile append-only saklar.
- Rating trajectory, review-count velocity ve breakpoint analizi snapshot'lar
  biriktikçe oluşur.
- İlk dönemde mevcut yorumların tarihleri, puanları, metinleri, sentiment ve
  keyword sinyalleri proxy olarak kullanılır.
- Idempotency cadence-aware olur. Cadence Faz 2'de (2026-07-25) `biweekly`'e
  düşürüldü (önce `weekly` idi); aynı venue, period ve review sıralaması
  yeniden çalıştırıldığında duplicate üretilmez. Cadence config ile
  `daily`/`weekly`/`biweekly` arasında değiştirilebilir; `biweekly` periyot
  sınırları `cadence_anchor_date`'e göre hizalanır (bkz. "Takip edilen mekan"
  bölümü). Eksik/başarısız venue'lar güvenli biçimde tekrar denenebilir.
- Adapter birden fazla zorunlu review-sort response'unu destekler (hepsi
  memory'de toplanır; snapshot, raw payload, review ve appearance kayıtları
  ancak tümü başarılı olduğunda tek DB transaction'ında yazılır, yarım
  snapshot commit edilmez) ama aktif config artık tek sort (`newest`) ister
  (bkz. "Periyodik fetch" bölümü).
- Ham snapshot'lar korunduğu için yeni bir score version geçmiş verinin
  tamamında `recompute` ile çalıştırılabilir.

Google verisinin kalıcı ham snapshot olarak saklanması için gerekli izinlerin
mevcut olduğu proje sahibi tarafından 2026-07-18 tarihinde kesin karar olarak
bildirilmiştir. Configuration/uyum kapısı bulunmayacak; ham yazım varsayılan ve
tek production davranışıdır.

## Provider adapter yaklaşımı

Fetch orchestration ve persistence, veri sağlayıcısından ayrılır. Ortak adapter
sözleşmesi normalize edilmiş venue state, ham response ve review kayıtlarını
döndürür. Task 1'de yalnızca official Places API adapter'ı uygulanır.

Gelecekteki bir task'ta üçüncü parti sağlayıcıdan son 6 aylık tam review
backfill eklenebilir. Bunun için şema review source değerini (`places_api`,
`backfill`) ve provider'a ait external kimlikleri taşıyabilir; Task 1'de
backfill adapter'ı veya üçüncü parti çağrı uygulanmaz.

## Discovery — Places API (New) Nearby Search + grid (Faz 2, 2026-07-24)

Venue seçimi `python -m app.discover` ile, webapp ve periyodik fetch'ten ayrı bir
adım olarak yapılır. 2026-07-24'te Faz 2 kapsamında mekanizma tamamen
değiştirildi: hedef "en iyi N'i seç"ten "hard filtreyi geçen neredeyse
herkesi al"a döndüğü için Text Search (New)'ün sorgu başına ~60 sonuç tavanı
yapısal olarak yetersiz kaldı (bkz. aşağıdaki "Nereden buraya" notu).

- **İki bölge:** Eryaman (`config/data_collection.eryaman.yaml`) ve Armada
  (`config/data_collection.armada.yaml`, Söğütözü — 2026-07-25'te Batıkent'in
  yerine geçti, bkz. aşağıdaki "Bölge değişikliği" notu), her biri kendi
  `Region` DB kaydı, kendi merkez koordinatı (~16,6km ayrık, çakışmayan ~3km
  yarıçaplı çemberler — kullanıcı kararı, tek birleşik 15km alan yerine) ve
  kendi search cache/catalog/report dosyalarıyla. Tek bir
  `DataCollectionConfig` hâlâ tek bölgeyi temsil eder
  (`region: RegionConfig` singular alan);
  `app.discover`/`app.fetch` artık `--data-collection-config` bayrağıyla
  hangi dosyanın kullanılacağını seçer (`--catalog` deseniyle aynı, adı
  `--config` değil çünkü `app/scoring/recompute.py` o adı zaten "scoring
  config" için kullanıyor).
- **Grid tarama** (`app/discovery/grid.py`): her bölgenin `radius_meters`
  çemberi, `cell_radius_meters` boyutunda kare hücrelere bölünür; her karenin
  çevrel dairesi (yarıçapı `cell_radius_meters`) Nearby Search'e gönderilir —
  kareler düzlemi boşluksuz kapladığı için bu tüm bölgeyi de kapsar.
  `radius_meters=3000, cell_radius_meters=500` için 69 coğrafi hücre üretir
  (elle hesaplandı ve gerçek `search --max-requests 0` dry-run çıktısıyla
  doğrulandı).
- **Tip gruplama:** Nearby Search `includedTypes` başına en fazla 50 tip
  kabul eder; `config/data_collection.*.yaml`'daki `included_types` alanı
  Google Places API (New) Table A'nın **tüm** "Food and Drink" kategorisini
  içerir (~166 tip — yalnızca `restaurant`/`cafe` değil, `bistro`, `bakery`,
  `pastry_shop`, `dessert_shop`, `ice_cream_shop`, `candy_store` ve tüm
  mutfak-spesifik `*_restaurant` tipleri dahil — kullanıcı kararı: "yeme
  içmeyle alakalı tüm types"). Bu liste `chunk_types` ile ≤50'lik gruplara
  bölünür (~166 tip için 4 grup); gerçek "arama birimi" coğrafi hücre × tip
  grubu kombinasyonudur (`GridCellState`, `cell_id` örn. `"r2c3.batch0"`) —
  bu yüzden Eryaman/Armada'nın taraması tam olarak ~69×4=276 arama birimi
  yapar (Armada için 2026-07-25'te zero-cost dry-run'la da doğrulandı: 276) —
  bu artık kesin bir sayıdır (bkz. aşağıdaki "tavana çarpma" notu:
  bölme kaldırıldığı için sabit kalır, büyümez).
- **Tavana çarpma: bölme yok, sabit istek sayısı (2026-07-24'te revize edildi).**
  İlk tasarımda bir birim tam `max_result_count` (20) döndürürse (kırpılma
  ihtimali) yarı yarıçaplı 4 alt birime bölünüyordu (`split_cell`, tek
  seviye). **İlk gerçek canlı Eryaman koşusunda bu kaldırıldı:** 276 temel
  istekten 45'i (~%16) tavana çarptı, her biri 4 alt istek doğurdu ve toplam
  456'ya çıktı (+%65) — kullanıcı bunun öngörülemezliğini kabul edilemez
  buldu ve sınır taşması gibi küçük hassasiyet kayıplarını önemsemediğini
  belirtti (`rejected_outside_radius` zaten var). Karar: tavana çarpan birim
  artık **hiç bölünmez**, sonucu olduğu gibi kabul edilip yalnızca
  `cells_flagged_for_review`'da işaretlenir. Böylece bir bölgenin toplam
  arama isteği her zaman tam `hücre × tip-grubu` kadardır — dry-run'da
  görülen sayı kesindir, sürpriz artış olmaz. Bedeli: en yoğun ceplerde
  (rankPreference=POPULARITY'nin en sona bıraktığı, genelde en az review'lu)
  bazı mekanlar görülmeyebilir. `split_cell` ve ilgili tek-seviye derinlik
  mantığı koddan silindi; `GridCellState.depth`/`parent_cell_id` alanları ve
  `status="split"` değeri yalnızca **eski (Eryaman'ın ilk koşusundaki)**
  cache kayıtlarıyla geriye dönük uyumluluk için şemada kaldı — yeni hiçbir
  hücre bunları kullanmayacak. `cells_flagged_for_review`, `depth>=1`
  yerine `status=="searched" and hit_result_cap` olarak yeniden tanımlandı
  (hem eski split-parent'ları doğru şekilde hariç tutar hem yeni,
  bölünmeyen tavana-çarpan hücreleri doğru yakalar) — Eryaman'ın gerçek
  cache'i üzerinde doğrulandı: yeniden tanım öncesi/sonrası aynı sonucu
  (19) verdi.
- **Sınır filtresi:** kare-grid + çevrel daire yaklaşımı, kenar hücrelerin
  `radius_meters`'ın biraz dışına taşmasına izin verir (yerel olarak
  ~%15-30 — kasıtlı, kabul edilmiş bir yaklaşım). `apply_hard_filters` artık
  üçüncü bir ret nedeni içerir (`rejected_outside_radius`) — adayın gerçek
  koordinatı bölge merkezinden `radius_meters`'ı aşarsa elenir. Bu yüzden
  `DiscoveryCandidate`/`CachedCandidate` artık `latitude`/`longitude` taşır
  (önceden yalnızca Text Search adapter'ının kendi local radius filtresi
  içinde geçiciydi, artık cache'te kalıcı olarak saklanır).
- **Take-all seçim (hedef sayı yok):** `target_count`/`minimum_candidate_pool`
  ve seçimi hedef sayıya kırpan `select_candidates`/`DiscoverySelectionError`
  tamamen kaldırıldı. `apply_hard_filters`'ı (`OPERATIONAL` + minimum review
  count + bölge yarıçapı) geçen **her** aday, freshness'ı bilindiği anda
  kataloğa eklenir (`accept_all_candidates` — artık yalnızca insan-okur rapor
  için skor sıralaması yapar, seçim/kırpma yapmaz). Aynı markanın şube sayısı
  hâlâ sınırlanmaz (`brand_key`/`normalize_brand` yalnızca raporlama içindir).
- **`excluded_primary_types` filtresi (2026-07-24 eklendi):** Nearby
  Search'ün `includedTypes`'ı Google'ın kendi FAQ'sinde belirttiği gibi bir
  mekanın TÜM tip etiketlerine bakar (`includedPrimaryTypes`'tan farklı
  olarak, o yalnızca ana kategoriye bakar) — bu yüzden kuaför/market/klinik
  gibi yemekle ilgisiz mekanlar da ikincil bir food-tipi etiketiyle
  sonuçlara sızabiliyor. Gerçek Eryaman koşusunda (456 istek, 410 eligible
  aday) somut örnekler bulundu: `medical_clinic` (diyetisyen kliniği),
  `barber_shop`, `hair_salon`, `supermarket` (Bim), `store` (nargile
  dükkanı), `swimming_pool`, `amusement_center` (çocuk oyun evi),
  `video_arcade` (simülasyon merkezi) — 410'da 8 mekan (~%2). `apply_hard_filters`'a
  Google'ın atadığı `primary_type`'a göre local bir eleme eklendi
  (`rejected_irrelevant_primary_type`); bu, freshness'tan **önce** çalışır
  (`_filtered_candidates`/`freshness_shortlist` içinde), yani bu tip mekanlar
  için gereksiz Legacy Place Details isteği hiç atılmaz. Liste
  (`config/data_collection.*.yaml`'da) bu 8 kategoriyle başlıyor; 3 sınırda
  kalan kategori (`sports_complex` — "...Pool Cafe", `garden_center` —
  "Ankara Barbekü", `wedding_venue` — düğün salonu) isimlerinde yemek/ikram
  ima ettiği için kullanıcı kararıyla listeye eklenmedi. Zaten kataloğa
  girmiş 8 mekan, filtre eklendikten sonra kataloktan elle çıkarıldı ve
  `finalize` (local, ücretsiz) yeniden çalıştırılarak filtrenin onları
  tekrar eklemediği doğrulandı — hiçbir yeni API çağrısı yapılmadı.
- **Bölgeler arası koruma:** `provider_place_id` DB'de bölgeler arası GLOBAL
  unique'tir (`uq_venue_provider_place_id`, `app/models.py`); bir bölgede
  zaten kayıtlı bir `place_id`'nin başka bir bölgede ikinci kez taranıp
  eklenmesini önlemek için `app/catalog.py`'deki `load_other_region_place_ids`,
  `catalog.*.yaml` glob'unu tarayıp diğer tüm bölgelerin `place_id`'lerini
  toplar; bu küme hem freshness kontrolünden (boşuna ücretli çağrı
  yapılmasın diye) hem finalize'dan hariç tutulur. DB constraint'i son çare
  güvenlik ağıdır (Eryaman/Armada çemberleri ~16,6km ayrık ve çakışmadığı
  için bu normalde tetiklenmez).
- Discovery field mask yorumsuz ve minimaldir: place ID, display name,
  business status, user rating count, type ve konum
  (`app/adapters/places_nearby.py`, `NEARBY_SEARCH_FIELD_MASK`).
- Ücret kontrolü için discovery hâlâ staged çalışır: `search`, `freshness`,
  `finalize`. `search --max-requests 0`, hiçbir API çağrısı yapmadan yalnızca
  grid'i hesaplayıp `total_cells` gösterir — yeni bir bölge veya
  `cell_radius_meters` denemesi için ücretsiz bir "dry-run" olarak kullanılır.
- Search birimleri ve normalize adaylar `data/discovery-search-cache.<bölge>.json`
  içinde checkpoint edilir (cache versiyonu artık `discovery-search.v2`).
  `finalize` ağ çağrısı yapmaz.
- Discovery seçimi otomatiktir. Proje sahibi raporu denetler fakat normal
  akışta manuel venue seçimi yapılmaz.
- **Nearby Search SKU doğrulandı (2026-07-25):** Google'ın resmi
  dokümantasyonundan (`developers.google.com/maps/documentation/places/
  web-service/nearby-search`) doğrudan kontrol edildi: field mask'imizdeki
  `businessStatus` ve `userRatingCount` alanları Nearby Search'te
  **Enterprise SKU**'yu tetikliyor (`id`/`displayName`/`primaryType`/
  `location` yalnızca Pro olurdu, ama Google en yüksek kademeli alana göre
  fiyatlandırıyor — toplamıyor). Enterprise: aylık **1.000 istek ücretsiz**,
  sonrası **$35,00/1.000 istek**. Eryaman'ın 456 isteklik taraması tek
  başına, Armada'nın beklenen ~276 isteklik taraması da birlikte
  (456+276=732) aylık ücretsiz kotanın altında kalıyor — ayda bir kez her
  iki bölgeyi de `--reset` ile baştan taramak bile $0 maliyetli.

### Nereden buraya: Text Search tabanlı toplu keşif neden kaldırıldı

Faz 1'in Text Search (New) + tek genel sorgu + freshness-ayarlı "en iyi N'i
seç" mekanizması, sorgu başına ~60 sonuç tavanı yüzünden "neredeyse tüm
mekanları al" hedefiyle yapısal olarak uyumsuzdu. Ayrıca Text Search serbest
metin sorgusuna relevance ile eşleştiği için (`"restoran ve kafe"`), tipi
gerçekten restoran/kafe olan ama adı bu kelimeleri içermeyen mekanları
atlayabilirdi; Nearby Search'ün `includedTypes`'ı Google'ın kendi tip
taksonomisiyle doğrudan filtrelediği için tip-bazlı eksiksiz taramaya daha
uygun bir primitive'tir.

**Google Places Aggregate API değerlendirildi ve reddedildi:** bu API
(`computeInsights`, eski adıyla "Places Insights API") gerçek ve güncel bir
üründür; alan bazlı place_id listesi döndürebilir (`INSIGHT_PLACES` modu)
ama **yalnızca sayı ≤100 ise**, ve döndürdüğü şey **yalnızca place_id**'dir
(isim/rating/durum/tip yok — `ComputeInsightsResponse.placeInsights[].place`
sadece bir resource name string'i). Bu hem 100'lük tavanın Nearby Search'inkiyle
(20) benzer şekilde ince taneli tiling gerektirmesi hem de her place_id için
ayrıca bir Details çağrısı gerektirmesi (Nearby Search tek çağrıda hem
enumerasyon hem filtreleme metadata'sı verirken) yüzünden bu kullanım için
net bir verimlilik kazancı sağlamıyor; kullanılmadı. `INSIGHT_COUNT` modu
ileride grid hücre boyutunu ucuza kestirmek için bir yoğunluk-probu olarak
değerlendirilebilir ama bu şu an uygulanmadı/planlanmadı.

Kaldırılan kod: `SearchQueryState`/`SearchPageRecord` (sayfalama tabanlı cache
şeması), eski `DiscoverySearchStage` (`complete_search_if_pool_ready` dahil),
`app/adapters/places_new.py`/`PlacesNewTextSearchAdapter`,
`DiscoveryQueryConfig`, `select_candidates`/`DiscoverySelectionError`,
kullanılmayan (yalnızca kendi testinden çağrılan) `DiscoveryService` sınıfı ve
`PlaceDiscoveryProvider`/`PagedPlaceDiscoveryProvider`/`DiscoveryPage`.

### Bölge değişikliği: Batıkent → Armada (2026-07-25)

İkinci bölge olarak planlanan Batıkent'te hiçbir gerçek API çağrısı hiç
yapılmamıştı (katalog hep boştu) — kullanıcı kararıyla tamamen iptal edildi,
yerine **Armada** (Söğütözü, `39.911640, 32.809945`) geldi. Eski
`config/catalog.batikent.yaml`/`config/data_collection.batikent.yaml`
silindi (git'ten de kaldırıldı, geri dönüş ihtimaline karşı dursun
denmedi); yerine aynı şablondan `config/catalog.armada.yaml`/
`config/data_collection.armada.yaml` üretildi — yalnızca `region`
(slug/name/center) ve `brand_stopwords` (`ankara`, `armada`, `söğütözü`,
`sogutozu`) bölgeye özel, geri kalan her şey (166 tip, filtreler,
`tracked_venue_limit`, cadence) Eryaman'la birebir aynı.

Kullanıcı "r=3km mantıklı mı?" diye sordu; WebSearch ile Söğütözü'nün
gerçek bir yeme-içme yoğunluğu olan bir bölge olduğu (iş merkezi + sosyal
yaşam kesişimi, çok sayıda kafe/restoran) doğrulandı, ardından zero-cost
`search --max-requests 0 --reset` dry-run'ı çalıştırıldı: **276 hücre** —
Eryaman'la birebir aynı (aynı `radius_meters=3000`/`cell_radius_meters=500`
salt geometriden gelen bir sayı, konumdan bağımsız). Eryaman-Armada merkez
mesafesi `app/discovery/geo.py`'nin kendi `distance_meters` fonksiyonuyla
hesaplandı: **~16,6km** — 2×3km=6km çakışma eşiğinin çok üzerinde, bölgeler
arası koruma mekanizmasının normalde hiç tetiklenmeyeceği teyit edildi.
Henüz hiçbir gerçek Nearby Search/freshness API çağrısı yapılmadı; sıradaki
adım onaylı dry-run/smoke/tam koşu aşamalarıdır (Eryaman'da izlenen akışın
aynısı).

## Periyodik fetch — Places API Legacy (2026-07-25 itibarıyla supersede edildi)

> **Supersede:** Periyodik snapshot artık Apify ile alınıyor (bkz. "Review
> backfill + Scoring v6" — Apify `totalScore`/`reviewsCount`/`title` agregatı da
> verdiği için `place_snapshots`'ı o üretiyor). Aşağıdaki Google Place Details
> akışı (kod + testler) çalışır durumda tutuluyor ama biweekly toplama için artık
> `app.backfill fetch` kullanılıyor. Discover hâlâ Google Nearby Search'te.

- Webapp canlı provider araması yapmaz; yalnızca DB/catalog venue'larını arar.
- Fetch venue seçmez, bölgeye özel `config/catalog.<bölge>.yaml` içindeki
  `place_id` kayıtlarını işler (`--catalog`/`--data-collection-config` ile
  seçilir). Kataloğa ekleme discovery üzerinden yapılır.
- Cadence `biweekly`'dir (2026-07-25, Faz 2; önce `weekly`), `cadence_anchor_date`'e
  hizalanır; config değişikliğiyle `daily`/`weekly`'ye de dönülebilir.
- Review içeren tüm çağrılar Legacy Place Details üzerinden yapılır.
- Her venue için yalnızca `reviews_sort=newest` çağrısı yapılır (2026-07-25,
  Faz 2; önce `newest`+`most_relevant` ikisi de yapılıyordu — bkz. "Takip
  edilen mekan" bölümündeki gerekçe). Adapter (`PlacesLegacyAdapter`) genel
  olarak birden fazla sort'u hâlâ destekler, yalnızca aktif
  `FetchConfig.review_sorts` tek elemanlı.
- Review metninin ve dedup anahtarının çağrılar arasında stabil kalması için
  `reviews_no_translations=true` kullanılır.
- Her response ham payload olarak kendi request variant bilgisiyle saklanır.
- Birden fazla sort aktifken (bugün değil, ama adapter'ın genel yeteneği)
  aynı review'un iki sıralamada da görülmesi durumunda canonical review
  logical snapshot içinde tek kez yazılır; her sıralamadaki görünümü ve rank
  bilgisi appearance kayıtlarında ayrıca korunur.
- Periyodik fetch field mask'i minimaldir: `name`, `business_status`, `rating`,
  `user_ratings_total`, `price_level`, `reviews`. `fields` sort'tan bağımsızdır
  — tek sort'a düşmek `rating`/`price_level`/`business_status` kaybına yol
  açmaz.
- Timeout, sınırlı retry/backoff, hata sınıflandırma ve fetch-run özeti bulunur.
  Live fetch'te `--no-retries` adapter retry sayısını sıfıra indirir; böylece
  `takip edilen (tracked) venue sayısı × 1 review sort` için onaylanan azami
  HTTP isteği teknik olarak aşılmaz (bölge başına kataloğun büyüklüğü sabit
  değildir ama tracked alt kümesi `tracked_venue_limit` ile üstten
  sınırlıdır; `--plan` çıktısı gerçek sayıyı verir).
- **Seed-safety bugfix (2026-07-25):** freshness aşamasının cache'lediği
  `newest` payload'u yalnızca `fields=reviews` ile alınır (`name` içermez).
  Eski `reusable` mantığı bunu sort eşleşmesine göre (state içerip
  içermediğine bakmadan) "yeniden kullanılabilir" sayıyordu; dual-sort
  rejiminde bu zararsızdı çünkü `most_relevant` her zaman taze ve tam-alanlı
  çekiliyordu, dolayısıyla state başka bir payload'dan geliyordu. Tek-sort
  (`newest`-only) rejiminde bu, hiç HTTP isteği yapmadan state'siz bir
  payload'la `fetch_place`'in çökmesine yol açardı
  (`PlacesApiError("...contains no venue state")`). Düzeltme:
  `app/adapters/places_legacy.py`'deki `reusable` artık yalnızca `result.name`
  içeren payload'ları seed olarak kabul eder; state'siz bir seed varsa
  `missing_sorts`'a düşer ve taze, tam-alanlı bir istek yapılır. Sonucu:
  freshness seed reuse artık pratikte hiç HTTP tasarrufu sağlamaz (tek sort
  zaten her zaman eksik sayılır) — kabul edilen, bilinçli bir basitleştirme.
- Yeni snapshot'taki provider name değeri bir önceki tamamlanmış snapshot'tan
  farklıysa `venue_name_changed` koduyla WARNING log üretilir. Aynı şekilde
  `business_status` değişirse `venue_status_changed` WARNING'i üretilir; ikisi
  aynı snapshot'ta birlikte gerçekleşirse iki ayrı warning kaydı oluşur. Önceki
  ve yeni değer fetch özetinde gösterilir. Bu kontroller yalnızca
  operasyoneldir; score ve confidence'ı etkilemez ve venue kataloğunu otomatik
  değiştirmez.
- `python -m app.fetch --plan`, provider'a hiç çıkmadan hangi venue'ların
  atlanacağını (`skip_existing`), hangilerinin freshness cache'inden seed
  alarak tek istekle (`fetch`, seeded) veya iki istekle (`fetch`/`new_venue`)
  işleneceğini ve toplam beklenen HTTP istek sayısını JSON olarak basar.
  `--plan` API key gerektirmez ve DB'ye yazmaz; `--venue` ile birlikte
  kullanılabilir. Çıktı hem retry'sız mantıksal sayıyı
  (`estimated_http_requests`) hem de `max_retries` etkinken gerçek üst sınırı
  (`worst_case_http_requests_with_retries` = mantıksal sayı ×
  (`max_retries`+1)) ayrı ayrı gösterir; 2026-07-24'te eklendi çünkü ilk
  implementasyon yalnızca retry'sız sayıyı gösteriyordu ve retry açıkken
  (varsayılan, `--no-retries` verilmediğinde) onay akışının dayandığı "azami
  istek sayısı" iddiasını gerçek dışı bırakıyordu.
- Legacy endpoint erişilemez olursa otomatik olarak başka endpoint/provider'a
  geçilmez; durum proje sahibine bildirilir ve alternatif birlikte kararlaştırılır.

## Takip edilen mekan (tracked) seçimi ve iki haftalık cadence (Faz 2, 2026-07-25)

Eryaman kataloğu 432 mekana çıktıktan sonra hepsini 2 haftada bir Legacy
Detail ile izlemek gereksiz maliyetti. Kullanıcı kararı: yalnızca
`user_ratings_total`'a göre en popüler `tracked_venue_limit` (varsayılan
`200`) kadarını aktif izle, geri kalanı kataloğda tut ama fetch etme. Bu
**sabit bir seçim değil** — her `finalize` (aylık discover döngüsünün son
adımı) koşusunda yeniden hesaplanır, böylece review sayısı büyüyen bir mekan
sonraki bir döngüde tekrar top-N'e girebilir.

- **Şema:** `venues.is_tracked` (migration `0004_add_venue_is_tracked`,
  `default=true`; `0003_drop_unused_snapshot_fields`'ın devamı). Katalogda
  karşılığı `VenueCatalogEntry.tracked: bool = True` ve
  `VenueCatalogEntry.user_ratings_total: int | None = None` (sıralama için
  kalıcı referans — bu turda taranmayan bir mekan son bilinen değerini
  korur). `is_active` ile aynı iki-katmanlı (catalog → DB) senkron deseni:
  `sync_catalog` her iki alanı da `Venue`'ya yazar.
- **Sıralama (`app/discovery/selector.py`, `rank_tracked_venues`):** saf
  fonksiyon, DB veya IO'ya dokunmaz. Girdi: mevcut kataloğun tamamı (eski +
  bu turun yeni adayları) ve bu turda taranan `place_id → user_ratings_total`
  haritası. Her entry için: bu turda tarandıysa değer güncellenir, yoksa
  entry'nin zaten sahip olduğu (varsa) değer korunur. Bir değeri **olan**
  tüm entry'ler azalan sıralanır (eşitlikte `place_id` artan — mevcut
  `accept_all_candidates`'daki tie-break deseniyle tutarlı), ilk `limit`
  kadarı `tracked=True`. Hiç değeri olmayan (ne bu turda ne daha önce
  bilinen) entry'ler mevcut `tracked` durumunda **dokunulmadan** bırakılır —
  veri yokken ne cezalandırma ne ödül var. Liste sırası (YAML insertion
  order) korunur.
- **`finalize` entegrasyonu:** `build_discovery_result` yeni bir
  `all_scanned_candidates` parametresi alır (`app/discover.py`'de
  `deduplicate_candidates(cache.domain_candidates())` — bu turun ham, dedup
  edilmiş tüm adayları, yeni + zaten katalogda olanlar dahil). Yeni entry'ler
  her zamanki gibi kurulduktan sonra `(*existing, *new_entries)`
  `rank_tracked_venues`'a verilir; sonuç katalog bu şekilde yazılır. Rapora
  `tracked_count`/`not_tracked_count` eklendi.
- **Yeni mekan koruması yok (kullanıcı kararı, 2026-07-25):** Google Places
  API açılış tarihi vermez (ne Legacy ne New); en eski review tarihi de
  güvenilir bir proxy değil (yalnızca gördüğümüz birkaç review'un en eskisi).
  `rank_tracked_venues` yeni-keşfedilen mekanlara özel bir dokunulmazlık
  tanımaz — düşük review sayısıyla başlayan bir mekan organik olarak review
  biriktirdikçe sonraki aylık döngülerde doğal yoldan yükselip top-N'e
  girebilir.
- **Cadence: `biweekly` (2026-07-25, önce `weekly`):** `app/cadence.py`,
  `period_start_for`'a `anchor_date: date | None` parametresi eklendi.
  Önce mevcut haftalık mantıkla snapshot'ın ve anchor'ın kendi hafta
  başlangıçları bulunur; aralarındaki hafta farkı (`(week_start -
  anchor_week_start).days // 7`) tek sayıysa bir hafta geri kayılır (çift
  haftalık periyodun başına iner). `FetchConfig.cadence_anchor_date`
  (`biweekly` iken zorunlu, validator ile kontrol edilir) config'te tutulur;
  Eryaman/Armada için `2026-07-13` (bir Pazartesi, Faz 1'in ilk
  period_start'ı — keyfi ama anlamlı bir referans).
  `FetchConfig.review_sorts` validator'ü de `{"newest", "most_relevant"}`
  yerine `{"newest"}` zorunlu kılacak şekilde daraltıldı.
- **Zamanlama hâlâ elle:** discover (search→freshness→finalize, retarget'ı
  da içerir) ayda bir, fetch iki haftada bir; proje sahibi doğal dille
  tetikler ("2 hafta oldu detail çağrını yap" gibi). Otomasyon fikri "Faz
  4'te netleştirilecek" bölümünde artık bu somut mekanizmaya bağlı.
- **Aylık discover `--reset` gerektirir (2026-07-25 netleşti):**
  `app.discover search`'ün cache'i `search_completed=true` olduktan sonra
  tekrar çağrılması **sıfır yeni istek** yapar (yalnızca durumu yazdırır) —
  keşfedilen hücreler asla otomatik yeniden taranmaz. Bu, iki gerçek sonuç
  doğurur: (1) yeni açılan bir mekan `--reset` olmadan asla bulunamaz; (2)
  `rank_tracked_venues`'ın kullandığı `current_review_counts`
  (`cache.domain_candidates()`'tan gelir) de dondurulur — `app.fetch`'in
  biweekly topladığı güncel review sayıları asla `finalize`'ın sıralamasına
  girmez (`_run_finalize` hiçbir zaman DB'ye bağlanmaz, yalnızca cache/
  katalog dosyalarını okur). Yani `--reset` olmadan hem yeni mekan keşfi
  hem de dinamik yeniden sıralama fiilen çalışmaz. Karar: aylık discover
  akışına `search --reset` **standart, zorunlu bir adım** olarak eklenir —
  yukarıdaki SKU doğrulamasına göre bu maliyetsiz (aylık 732 istek < 1.000
  ücretsiz kota). `--reset` sonrası `existing_place_ids` filtresi zaten yeni
  aday havuzunu (freshness için) mevcut kataloğa daraltıyor, ama
  `all_scanned_candidates` (dedup edilmemiş `domain_candidates()`) hem yeni
  hem zaten-katalogtaki adayların güncel review sayısını taşıdığı için
  ranking doğru şekilde tazeleniyor — kod bu senaryo için zaten doğru
  tasarlanmıştı, ek bir düzeltme gerekmedi.

## Review backfill + Scoring v6 (Faz 3, 2026-07-25)

Places API her fetch'te bir mekanın yalnızca ~5 review'unu veriyor ve agregat
rating popüler mekanlarda atıl (3000+ review'lu bir yerde 300 taze 1-yıldız
ortalamayı oynatmaz). Bu iki sinyali zayıflatıyor: `sentiment_keyword_drift`
(5-10 metinle gürültü) ve `rating_trajectory` (yavaş + agregat atıl). Çözüm:
**Apify Google Maps Reviews Scraper actor**'üyle her tracked mekanın son ~12
ayının en yeni ~50 review'unu çekip `venue_reviews` corpus'una almak.

- **Mimari ilke (güncellendi 2026-07-25):** Apify her review item'ında mekanın
  agregatını da (`totalScore`→rating, `reviewsCount`→user_ratings_total,
  `title`→name) verdiği için **tek koşu hem `place_snapshots` hem `venue_reviews`
  corpus'unu üretir** ve paralı Google Place Details fetch'ini supersede eder
  (`app.fetch` kod/test olarak duruyor ama artık kullanılmıyor; discover Google
  Nearby Search'te kalıyor). Agregat hâlâ Google'ın gösterdiği değer (Apify onu
  okur) → ground-truth kaybı yok. `source=backfill` ayrımı review corpus'u için
  korunur.
- **Apify paralı servis, projemizin içinden çağrılır:** `APIFY_TOKEN`
  `.env`'de (Settings'te `SecretStr`); `apify-client` Python SDK dependency olarak
  eklendi ama **lazy import** — yalnızca gerçek `fetch` çağrısında yüklenir, modül
  ve testler onsuz çalışır. Places API'yle aynı disiplin: `fetch --plan` maliyet-
  şeffaf ön izleme (mekan sayısı, `reviews_limit`, cutoff, tahmini review, cost
  note), onay sonrası gerçek çağrı. Fiyat pay-per-event ~$0.30/1000 review; 200
  mekan × 50 = üst sınır ~$3 (Apify'ın aylık $5 ücretsiz kredisi karşılayabilir).
  **Not:** (İki iterasyon önce local SeleniumBase `google-reviews-scraper-pro`
  denenmişti — çok yavaş; sonra Outscraper API — çok pahalı ($3/1000); Apify
  hem API hem ~10× ucuz olduğu için ona geçildi.)
- **place_id join (temiz):** Apify her review item'ında Google'ın `ChIJ...`
  `placeId`'sini döndürüyor → join doğrudan `Venue.provider_place_id` üzerinden
  (eski araçtaki slug/custom-param köprüsüne gerek kalmadı). Eşleşmeyen
  place_id'ler raporda `unmatched_place_ids` olarak listelenir.
- **`fetch` komutu:** tüm tracked place_id'leri **tek bir Apify run**'ında
  `client.actor("compass/google-maps-reviews-scraper").call(run_input={placeIds,
  maxReviews=50, reviewsSort='newest', reviewsStartDate='365 days',
  language='tr', reviewsOrigin='all', personalData=True})` ile çalıştırır (Apify
  kuyruğu içeride yönetir, biz batch'lemeyiz), sonra dataset'i iterate eder. Ham
  yanıt `data/apify-<region>.json`'a (gitignored) **persist'ten önce** yazılır
  (paralı veri kaybolmasın diye), sonra tek session'da `persist_reviews` (corpus)
  + `persist_snapshots` (agregat snapshot) + `recompute_region` (v6) çalışır.
  Cadence/period/snapshot_date `data_collection.<region>.yaml`'dan gelir.
- **Filtre:** `reviewsSort='newest'`, `maxReviews=50`, `reviewsStartDate` = 12 ay
  önce (relatif "365 days"). Yoğun mekan maxReviews'e çarpar, sakin mekan tüm
  yılını verir. Sabit sayı drift için zaman-span'i garanti etmez ama cutoff eder.
- **`venue_reviews`:** venue'ya bağlı corpus (bkz. dataModel.md). `persist_reviews`
  Apify'ın düz review-item listesini alır (her item `placeId` taşır), place_id
  ile Venue'ya çözer, `(venue_id, dedup_key)` upsert (idempotent). Parse:
  `publishedAtDate` (ISO 8601; date-only fallback), `stars` (1-5), `text`
  (`textTranslated` fallback), `name` (reviewer; `reviewerId` fallback),
  `reviewDetailedRating` → `sub_ratings` (kategori yıldızları Food/Service/
  Atmosphere; reviewer doldurmadıysa Apify `{}` yollar → None saklanır).
  `dedup_key` `reviewId`'den (varsa), yoksa içerik-hash'i. Kaydedilmiş bir JSON
  `app.backfill import --input` ile de (yalnızca corpus'a) alınabilir (çağrı olmadan).
- **`place_snapshots` (Apify):** `persist_snapshots` her mekanın Apify
  agregatından (`totalScore`→rating, `reviewsCount`→user_ratings_total,
  `title`→provider_name = name-change kaynağı) bir snapshot üretir;
  `FetchRun(provider="apify")` altında, `(venue, cadence, period_start)` idempotent
  (Google path'iyle aynı). `business_status` ve `price_level` Apify reviews
  çıktısında **yok → NULL**; business_status kaybını **dormancy sinyali**
  karşılıyor (kapanan mekan yeni review almaz), price_level zaten skorda
  kullanılmıyordu. name değişince `venue_name_changed` WARNING (status WARNING'i
  düştü). Snapshot'a payload/SnapshotReview yazılmaz — scoring corpus'u tercih
  ediyor, agregatı snapshot'tan okuyor.
- **Scoring v6 (corpus-driven sinyaller):** `ScoringEngine.compute` artık
  `list[ReviewInput]` alıyor (Protocol: dedup_key/published_at/rating/text; hem
  SnapshotReview hem VenueReview sağlıyor). `compute_venue_score` corpus varsa
  onu, yoksa SnapshotReview'ı geçiriyor (`_reviews_for_scoring`). İki sinyal
  doğrudan corpus'tan üretiliyor:
  - `rating_trajectory` **count-split**: corpus tarihe göre sıralanıp newest yarı
    vs older yarı (takvime göre değil, **sayıya** göre) yıldız ortalaması
    karşılaştırılır — 50 review kaç günü kaplarsa kaplasın çalışır (yoğun mekanın
    newest 50'si haftalar, sakin mekanınki yıllar). `< 2×review_min_per_split` ise
    agregat snapshot deltasına fallback. `details.mode` = `review_split` /
    `aggregate_snapshot`.
  - `stability` **review-consistency**: corpus 5 zaman-sıralı bucket'a bölünür,
    bucket yıldız-ortalamalarının stddev'i seviye oynaklığını verir
    (`>review_max_level_stddev` = 0.65, 10'luk bucket integer-rating gürültü
    tabanı ~0.38'in üstünde → volatile; `≥high_rating_threshold` → stable_high;
    yoksa stable_low). Snapshot birikmesini **beklemeden** `available` olduğundan
    `early_phase_cap` (0.45) yalnızca ne snapshot ne corpus'u olan mekanlara
    kalıyor. Corpus yoksa v5 snapshot-volatilite fallback. `details.mode` =
    `review_consistency`.
  `sentiment_keyword_drift` de ~50 review'la besleniyor (5-10 değil). Score
  girdisi değiştiği için **v6**; v5 frozen (`review_split_enabled` /
  `review_stability_enabled` config default'ları False, v5 config bunları
  içermediğinden davranışı hiç değişmiyor). Aktif `SCORING_CONFIG_PATH`
  (app/config.py default + `.env`) `scoring.v6.toml`.
- **Zamanlama (operasyonel plan, 2026-07-26):** discover + Apify snapshot **ayda
  bir** elle çalıştırılır (yeni snapshot + corpus tazeleme). **Not:** `cadence`
  config şu an `biweekly`; aylık period bucket istenirse `period_start_for`'a
  küçük bir "monthly" eklemesi gerekir (Armada task'ıyla değerlendirilecek).
- **Sonraki iterasyon (not):** sub-rating (Servis/Yemek/Temizlik) kategori-drift
  sinyali — Apify `sub_ratings`'i corpus'ta (`venue_reviews.sub_ratings`) topluyor
  ama henüz skora girmiyor; ayrı bir kategori-drift sinyali eklenebilir.
  (`stability` review-consistency artık uygulandı.)

## Configuration ve secrets

- API key yalnızca environment üzerinden alınır; kodda veya version control'da
  bulunmaz.
- `.env` commit edilmez, `.env.example` sağlanır.
- Her bölgenin venue kataloğu discovery tarafından kendi `config/catalog.<bölge>.yaml`
  dosyasına yazılır (Eryaman, Armada). Yeni bir bölge eklemek elle bir config
  + boş katalog dosyası oluşturmaktan ibarettir, code değişikliği gerektirmez.
- Cadence, bölge yarıçapı, grid hücre boyutu, aranacak type listesi, filtre
  eşikleri ve freshness cezası hardcode edilmez; data-collection config'tedir.
  Category kotası, brand şube sınırı ve hedef venue sayısı (`target_count`)
  ürün kararıyla tamamen kaldırıldı (bkz. Discovery bölümü) — discovery artık
  hard filtreyi geçen herkesi alır, bir "N tanesini seç" kavramı yok.
- Score weight ve normalization parametreleri versioned config olarak tutulur.

## Faz 2'de netleştirilecek

- ~~Venue kataloğunun 30'dan 40 kayda code değişikliği olmadan çıkabildiğinin
  doğrulanması~~ ve ~~Places Aggregate API ile genişleme~~ 2026-07-24'te ele
  alındı: discovery artık grid tabanlı Nearby Search ile hard filtreyi geçen
  herkesi alıyor (bkz. Discovery bölümü), sabit bir hedef sayı kavramı yok;
  Places Aggregate API değerlendirilip reddedildi. Ankara genelinde tüm
  şehre yayılma (Eryaman+Armada ötesi) hâlâ açık bir gelecek adımı.
- Kullanıcı talebiyle kataloğa venue ekleme akışı gelirse Autocomplete tabanlı
  canlı arama/tamamlama.
- Katalog kurulumunda venue başına 1-2 Place Photo saklanması ve kartta
  `html_attributions` ile gösterilmesi.
- Places New `generativeSummary` ve `reviewSummary` alanlarının Eryaman'da
  bulunabilirlik testi. Uygunsa opsiyonel New Details snapshot çağrısı, Gemini
  ibaresi ve `reviewsUri` atıflarıyla UI gösterimi değerlendirilecek. Bu
  özetler hiçbir durumda score sinyali olmayacak.

## Faz 4'te netleştirilecek

- **Zamanlama otomasyonu (2026-07-24 kullanıcı notu, 2026-07-25'te
  mekanizma netleşti):** discover (search→freshness→finalize, ayda bir) ve
  fetch (`biweekly` cadence, `cadence_anchor_date`'e hizalı, iki haftada
  bir) artık somut, çalışan bir mekanizma (bkz. "Takip edilen mekan"
  bölümü) ama ikisi de kullanıcı tarafından elle tetiklenir ("2 hafta oldu
  detail çağrını yap" gibi), bir scheduler'a bağlı değildir. Faz 4'te bu
  muhtemelen scheduled bir pipeline'a (örn. Jenkins) bağlanacak — böyle bir
  otomasyon, `cron`'un takvim-tabanlı doğası "iki haftada bir" gibi
  epoch-tabanlı bir periyodu ifade edemediğinden `cadence_anchor_date` ile
  aynı parity kontrolünü job seviyesinde de ayrıca uygulamalı. Şimdilik
  yalnızca not düşüldü, tasarım/implementasyon yapılmadı.

## Scoring v5

İlk dört-sinyalli momentum tasarımı `scoring.v1` olarak geçmiş karar kaydında
korunur. Yüksek seviyesini istikrarlı biçimde koruyan mekanları ödüllendirmek
için stability eklenen beş-sinyalli tasarım `scoring.v2` olarak geçmiş karar
kaydında korunur. Structural changes sinyalinin tamamen çıkarıldığı tasarım
`scoring.v3` olarak geçmiş karar kaydında korunur. Stability'nin ürün açısından
daha önemli olduğunun kesinleşmesiyle ağırlık dağılımı `scoring.v4` olarak
versioned edilmiştir (bu keyword word-boundary bugfix'ini de aynı version
içinde barındırır, bkz. 2026-07-24 kaydı). Stability sinyaline "durgunluk
(dormancy)" kavramının eklenmesiyle `scoring.v5` versioned edilmiştir.
`rating_trajectory` ve `stability`'nin backfill-corpus'undan üretilmesiyle
(count-split trajesi + review-consistency istikrarı, bkz. "Review backfill +
Scoring v6" bölümü) aktif tasarım `scoring.v6` olarak versioned edilmiştir;
`app/config.py`'nin varsayılan `scoring_config_path`'i ve gerçek `.env` dosyası
`config/scoring.v6.toml`'a güncellenmiştir. v5 frozen kalır
(`review_split_enabled`/`review_stability_enabled` default'ları False olduğundan
hâlâ yüklenebilir ve davranışı değişmez).

Dört sinyal ve önerilen başlangıç ağırlıkları:

- Rating trajectory: `0.30`
- Review-count velocity/acceleration: `0.20`
- Review sentiment ve keyword drift: `0.20`
- Stability: `0.30`

Ağırlıkların toplamı `1.00` olur. `scoring.v4`, `scoring.v3`e göre review
velocity'den `0.05` alıp stability'ye ekler. Snapshot geçmişi yetersizken
stability unavailable kabul edilir ve mevcut ağırlık renormalization
mekanizması diğer sinyalleri yeniden dağıtır.

`business_status`, name değişimi ve `price_level` ham/parse edilmiş snapshot
verisi olarak korunur fakat hiçbir score signal, weight veya confidence
hesabına girmez. `price_level`, keyword drift için doğrulama veya destek
sinyali olarak da kullanılmaz; keyword drift yalnızca review içeriği ve zaman
pencereleri üzerinden çalışır.

Stability seviyeyle koşullu bir sinyaldir:

- Yüksek rating seviyesi + düşük dalgalanma: pozitif `stable_high` katkısı.
- Düşük rating seviyesi + düşük dalgalanma: `stable_low`; nötr veya config ile
  sınırlı hafif negatif katkı.
- Eşiğin üzerindeki dalgalanma: `volatile`.
- Uzun süredir hem rating sayısı hem review artışı durmuşsa: `dormant`
  (2026-07-24, `scoring.v5`).
- Yetersiz snapshot sayısı veya zaman kapsaması: `insufficient_data`.

`high_rating_threshold`, `window_days`, `min_snapshots`,
`max_rating_stddev`, `stable_high_value`, `stable_low_value` ve
`volatile_value` dahil tüm eşikler/değerler versioned scoring config'te
tutulur; scorer içinde hardcode edilmez.

**Dormancy (v5):** Yalnızca review tarihine bakmak yanlış olur — bir mekan
yeni review almadan da (yalnızca yıldız/oylama ile) aktif olabilir. Bu yüzden
"son aktivite tarihi", `user_ratings_total`'ın snapshot'lar arasında en son
arttığı tarih **veya** en son review'un `published_at`'i, hangisi daha
yeniyse, olarak hesaplanır (`ScoringEngine._days_since_activity`). Rating
sayısı hâlâ artıyorsa mekan fresh sayılır, ceza uygulanmaz. İkisi de durduysa,
`dormancy_grace_days` (60 gün) altında ceza yok; `dormancy_full_penalty_days`e
(365 gün) doğru ceza doğrusal artar ve `dormancy_penalty_value`e (-1.0)
ulaşır — bu, tam durgunlukta `stable_high`'ın (+0.75) bile net olarak negatife
dönmesini sağlar. Kısmi durgunlukta (`dormancy_penalty < 0` ama tam eşiğin
altında) state adı değişmez, yalnızca `value` ve `summary` etkilenir; tam eşiğe
ulaşınca state `dormant`'a döner. Bu ceza mekanı hiçbir zaman kataloğdan/
webapp'ten çıkarmaz, yalnızca `change_score`'u Bozdu yönüne çeker. Eski
`scoring.v4.toml` bu alanları içermediği için `StabilityConfig`'te bu üç alan
için nötr default'lar (`dormancy_penalty_value=0.0` vb.) tanımlıdır — v4
davranışı bu nedenle değişmeden kalır.

**Sınır durumu düzeltmesi (2026-07-24):** `user_ratings_total` tüm snapshot
geçmişi boyunca hiç artmamış VE hiç review yoksa (tam sessizlik, "kanıt yok"
değil), `_days_since_activity` artık en eski snapshot tarihini "son bilinen
aktivite" referansı sayıyor — önceden bu durumda `None` dönüp ceza hiç
uygulanmıyordu, yani bir yıldır tamamen sessiz `stable_high` bir mekan
cezasız kalabiliyordu. Bu bir v5 bugfix'idir (dokümante edilen "hem rating
hem review durursa ceza" niyetine karşı gerçek bir gedikti).

Task 1'de review tarihlerinden stability proxy üretimi varsayılan olarak kapalı
olacaktır. En fazla iki farklı sıralamadan gelen sınırlı ve seçilim yanlı review
örneği, güvenilir bir “istikrar” iddiası için yeterli kabul edilmez. Bu karar
ileride daha geniş review backfill verisi geldiğinde yeni bir score version ile
yeniden değerlendirilebilir.

Ana çıktı `change_score` (`-100..+100`) ve `confidence` (`0..1`) olur.
`stability_state` bardan bağımsız biçimde API/DB çıktısında korunur. Sade venue
kartında classification ve stability pill'leri gösterilmez; yalnızca genel
`Veri güveni` gösterilir. Sinyal bazındaki `reliability` değeri UI'da genel
güvenden ayrışması için `Kanıt gücü` olarak adlandırılır.

Change story yalnızca gerçek snapshot kapsaması kadar süre iddia eder; örneğin
“Son 90 günlük gözlemde yüksek seviyesini istikrarlı koruyor.” Gözlem süresi
yeterli değilken “X yıldır/aydır” ifadesi üretilmez.

2026-07-24'te keyword eşleşmesi substring'den kelime sınırına (`\bkeyword\b`)
düzeltildi; bu bir v4 bugfix'idir (yeni score version açılmadı), mevcut v4
sonuçları düzeltilmiş mantıkla `recompute` edildi. Bilinen sınırlama: Türkçe
yüklem ekleri kök kelimeye bitişik eklendiği için (`tazeydi`, `pahalıydı` gibi)
kelime sınırı bu çekimli biçimleri yakalamaz; sıfır eşleşmeli review'larda
mevcut rating-fallback (`(review.rating - 3) / 2`) bu durumu yumuşatır. Gerçek
bir Türkçe stemmer/morfolojik analiz bu kapsamın dışındadır.

## Çalışma komutları

Doğrulanmış temel komutlar:

```bash
uv sync
uv run alembic upgrade head
uv run python -m app.discover search --max-requests 0 --reset --data-collection-config config/data_collection.eryaman.yaml --catalog config/catalog.eryaman.yaml
uv run python -m app.discover search --max-requests 1 --reset --no-retries --data-collection-config config/data_collection.eryaman.yaml --catalog config/catalog.eryaman.yaml
uv run python -m app.discover status --data-collection-config config/data_collection.eryaman.yaml --catalog config/catalog.eryaman.yaml
uv run python -m app.discover freshness --max-requests N --no-retries --data-collection-config config/data_collection.eryaman.yaml --catalog config/catalog.eryaman.yaml
uv run python -m app.discover finalize --data-collection-config config/data_collection.eryaman.yaml --catalog config/catalog.eryaman.yaml
uv run python -m app.catalog
uv run uvicorn app.main:app --reload
uv run python -m app.fetch --region eryaman --plan
uv run python -m app.fetch --region eryaman
uv run python -m app.backfill fetch --region eryaman --plan
uv run python -m app.backfill fetch --region eryaman
uv run python -m app.backfill import --input data/apify-eryaman.json --region eryaman
uv run python -m app.scoring.recompute --region eryaman --score-version v6
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Armada için aynı komutlar `--data-collection-config config/data_collection.armada.yaml
--catalog config/catalog.armada.yaml` ile çalıştırılır.

Kontrollü ilk canlı deneme veya tek mekan retry işlemi için fetch komutuna
`--venue <slug>` filtresi verilebilir. Bu filtre yalnızca seçilen aktif katalog
kaydını işler; normal cadence-aware persistence ve scoring akışı değişmez.

## Container yaklaşımı

- Dockerfile dependency'leri aynı `uv.lock` üzerinden kurar.
- Compose `web` servisi ve manuel çalıştırılan `fetch`/`discover` job
  profile/service'lerini içerir.
- SQLite dosyası bind mount veya named volume ile container dışında korunur.
- Cloud-specific database, queue veya scheduler bağımlılığı eklenmez.
- Image build, container migration/catalog smoke ve iki container koşusu
  arasında bind-volume persistence doğrulanmıştır.
