# İlerleme

## Genel durum

Phase 1 tamamlandı (2026-07-24). Task 1'in tüm checklist maddeleri ve push
öncesi son review'da bulunan düzeltmeler geçti. Nihai veri toplama
kararıyla otomatik discovery, YAML catalog ve cadence-aware fetch dönüşümü
açıldı (başlangıç cadence'i haftalıktı; Faz 2'de 2026-07-25'te `biweekly`'e
düşürüldü, bkz. aşağıdaki 2026-07-25 kaydı). `GOOGLE_MAPS_API_KEY`
yapılandırılmıştır fakat kullanıcı onayı olmadan hiçbir ücretli API koşusu
yapılmaz. Önceden terminal çıktısında görünmüş olan key kullanıcı tarafından
rotate edilmiştir; güncel key yalnızca `.env` içindedir.

## Task 1 checklist

### Proje ve dokümantasyon

- [x] Beş zorunlu memory-bank dosyasını oluştur.
- [x] Proje amacı, Phase 1 kapsamı ve Bozdu/Coştu kavramını kaydet.
- [x] Snapshot, çift review sıralaması, dedup, adapter, backfill hazırlığı ve
      scoring/recompute kararlarını kaydet.
- [x] README'yi kurulum, kullanım, mimari ve komutlarla güncelle.
- [x] `.env.example` ve kapsamlı `.gitignore` ekle.

### Proje iskeleti

- [x] Python 3.12+ ve `uv` tabanlı `pyproject.toml` oluştur.
- [x] `uv.lock` üret.
- [x] FastAPI/Jinja2 uygulama iskeletini kur.
- [x] pydantic-settings configuration katmanını kur.
- [x] ruff, pytest ve pre-commit yapılandırmasını ekle.

### Database

- [x] SQLAlchemy engine/session ve portable model base oluştur.
- [x] Region, venue, fetch-run ve snapshot tablolarını oluştur.
- [x] Raw payload, canonical review ve review appearance tablolarını oluştur.
- [x] Versioned score-result tablosunu oluştur.
- [x] İlk Alembic migration'ı üret ve upgrade/downgrade doğrula.
- [x] Cadence-aware `(venue_id, cadence, period_start)` idempotency migration ve
      testlerini tamamla.

### Fetch ve adapter

- [x] Provider adapter protocol/interface oluştur.
- [x] Places API Legacy adapter'ını explicit fields ile uygula.
- [x] `most_relevant` ve `newest` çağrılarını uygula.
- [x] Raw response persistence ve review deduplication uygula.
- [x] Timeout, retry/backoff ve hata raporlamayı uygula.
- [x] Name değişimi için score dışı WARNING ve fetch-summary kaydını uygula.
- [x] `python -m app.fetch --region eryaman` CLI komutunu tamamla.
- [x] Kontrollü canlı deneme ve retry için `--venue <slug>` filtresi ekle.
- [x] Places API (New) Text Search adapter ve pagination akışını tamamla.
- [x] Text Search restriction'ını resmi rectangle şemasına geçir ve config
      radius'unu local haversine filtresiyle kesin uygula.
- [x] Deterministik discovery filter/brand cap/quota/scoring seçicisini tamamla.
- [x] Discovery'yi bounded `search`, `freshness` ve local-only `finalize`
      aşamalarına ayır; resumable cache/checkpoint testlerini tamamla.
- [x] `app.discover` ile `config/catalog.yaml` ve seçim raporu üretimini tamamla.
- [x] Fetch'i yalnızca YAML catalog `place_id` kayıtlarını işleyecek hale getir.
- [x] Aynı cadence periodundaki ikinci koşunun duplicate üretmediğini doğrula.
- [x] Kullanıcı onayıyla official discovery çalıştır ve seçim raporunu denetle.
- [x] 30 adayın Legacy newest-review freshness kontrolünü tek onaylı koşuda
      tamamla (30/30 başarılı, retry yok).
- [x] 30 venue'luk nihai catalog ve discovery raporunu üret; SQLite'a sync et.
- [x] Freshness ham `newest` payload'unu cache'le ve aynı günkü ilk fetch'te
      yeniden kullan; duplicate bootstrap çağrısını fixture ile engelle.
- [x] İlk katalog koşusundan sonra discovery'yi tek birleşik cafe/restoran
      sorgusuna geçir ve category minimum kotalarını kaldır.
- [x] Config-driven minimum uygun aday havuzuna ulaşınca pagination'ı erken
      bitir; mevcut search'i üçüncü restaurant sayfasını çekmeden tamamla.
- [x] Ayrı kullanıcı onayıyla ilk official haftalık snapshot fetch'ini tamamla
      (30/30 snapshot, 60/60 HTTP response başarılı, retry yok).
- [x] HTTP client INFO loglarında API key içeren request URL'lerini bastır;
      kullanıcıya açığa çıkan key'i rotate etmesini bildir.
- [x] Provider'a çıkmadan venue/sort/cache-reuse ve azami HTTP istek sayısını
      gösteren `python -m app.fetch --plan` dry-run çıktısını ekle.
- [x] `business_status` değişimi için `venue_status_changed` operasyonel
      WARNING'i ekle (name-change warning'iyle aynı desende, score dışı).

### Scoring ve change story

- [x] Swappable scorer interface oluştur.
- [x] Versioned scoring config oluştur.
- [x] Rating trajectory signal'ını uygula.
- [x] Review velocity/acceleration signal'ını uygula.
- [x] Review sentiment ve keyword drift proxy'lerini uygula.
- [x] Seviyeyle koşullu stability signal ve state hesaplamasını uygula.
- [x] Change score ve confidence hesaplamasını uygula.
- [x] Açıklanabilir signal breakdown ve kısa change story üret.
- [x] Geçmiş snapshot'lar için recompute CLI komutunu tamamla.

### Webapp

- [x] DB-only venue search endpoint ve arayüzünü oluştur.
- [x] Venue detay/score REST endpoint'ini oluştur.
- [x] Bozdu/Coştu bar ve sinyal açıklamalarını içeren sade kartı oluştur.
- [x] Genel veri güveni ve son snapshot tarihini göster; classification,
      stability ve tekrar eden change-story pill/metinlerini detay kartından
      kaldır.
- [x] Responsive ve erişilebilir temel UI sağla.
- [x] Health endpoint ekle.

### Test ve runtime

- [x] Fetch/parse için gerçekçi fixture unit testleri yaz.
- [x] Review dedup ve dual-sort appearance testleri yaz.
- [x] Score calculation ve edge-case testleri yaz.
- [x] Database idempotency integration testleri yaz.
- [x] Web search/card smoke testleri yaz.
- [x] Gerçek DB verili 30 mekanlık genel Bozdu/Coştu skor panosunu, confidence
      görünümünü ve classification filtrelerini ana sayfaya ekle.
- [x] Dockerfile oluştur.
- [x] `web` ve profile tabanlı `fetch` içeren Compose dosyasını oluştur.
- [x] SQLite volume persistence'ı doğrula.
- [x] Tüm test, lint, format, migration ve smoke kontrollerini geçir.

## Faz 1 durumu: tamamlandı

Faz 1 kapsamındaki tüm Task 1 maddeleri (yukarıdaki checklist) tamamlanmıştır.
30'dan 40 kayda (ve sonrasında 500 mekana) code değişikliği olmadan
çıkabildiğinin doğrulanması artık Faz 1'i kapatan bir Task 2 ön koşulu olarak
değil, **Faz 2'nin** kapsamına taşınmıştır (2026-07-24 kullanıcı kararı);
Faz 2 zaten `techContext.md`'deki "Faz 2'de netleştirilecek" bölümünde 500
mekana genişleme işini içeriyordu, 30→40 doğrulaması bu genişlemenin ilk
adımı olarak oraya eklendi.

## Bilinen bug'lar

Kayıtlı yerel runtime bug yok. İlk onaylı Text Search isteğindeki `403`, Cloud
ayarı düzeltildikten sonra ortadan kalktı. İkinci onaylı istek request
shape'indeki `locationRestriction.circle` nedeniyle `400 INVALID_ARGUMENT`
döndürdü; adapter resmi rectangular restriction + local radius filtresine
geçirilerek fixture testleriyle düzeltildi. Üçüncü onaylı tek istek başarıyla 16
cafe adayı getirdi ve cafe search tek sayfada tamamlandı. Restaurant ikinci
sayfasından sonra minimum aday havuzu karşılandı; üçüncü sayfa çağrısı
yapılmadan search tamamlandı. İki search sorgusunda toplam 3 HTTP isteğiyle 50
ham / 47 unique aday checkpoint edildi; 31 uygun aday bulundu. Task 1 hedefi
30'a çıkarıldı ve freshness aşaması preliminary ranking ile tam 30 adayla
sınırlandı. 30 freshness isteğinin tamamı başarılı oldu. Local finalize 8 cafe
+ 22 restaurant içeren 30 kayıtlık kataloğu üretti. İlk full fetch sonrasında
30 snapshot, 60 raw payload, 289 deduplicate review,
300 review appearance, 30 `scoring.v3` ve 30 `scoring.v4` sonucu bulunuyor.
Stability ağırlığını `%30`a çıkaran v4 recompute tamamlandı; eski version
sonuçları korunuyor. DB-only gerçek mekan
arama/kart smoke testi geçti. Açık güvenlik işi: log çıktısında görünen API key
rotate edildi ve yeni key `.env` içine eklendi. Sonraki geliştirme işi birleşik
discovery sorgusu ve API çağrısı öncesi local dry-run/request planıdır.

Bilinen model riski: early-phase sentiment drift, recent/older cohort'lardan
birinde çok az review varken kanıt gücünü toplam review sayısından fazla yüksek
hesaplayabilir. Venice Italian Pizza bunun somut örneğidir. Config-driven cohort
minimumu ve dengeli reliability hesabı sonraki score version kararıdır.

## 2026-07-24 — Tam review sonrası düzeltmeler

Tam codebase review'ında bulunan iki gerçek bug düzeltildi:

- Ana sayfa skor panosu "son snapshot"ı `MAX(PlaceSnapshot.id)` yerine
  `snapshot_date` + `id` sıralı `row_number()` penceresiyle seçiyor artık;
  geçmişe dönük `--date` ile doldurulan bir hafta artık venue'yu skorborddan
  düşürmüyor.
- Sentiment keyword eşleşmesi substring yerine kelime sınırına (`\b`) geçirildi
  (`"bad"` artık `"badem"` içinde eşleşmiyor). v4 bugfix olarak ele alındı,
  yeni score version açılmadı; mevcut 30 venue `recompute` ile güncellendi ve
  bazı skorlar gerçekten değişti (örn. elmin-simit-cafe 29.7 → 35.5).

Ayrıca: `place_snapshots`'ta hiç dolmayan 6 kolon (`formatted_address`,
`latitude`, `longitude`, `types`, `website`, `google_maps_url`)
`0003_drop_unused_snapshot_fields` migration'ıyla kaldırıldı (upgrade/downgrade
doğrulandı); discovery tek birleşik sorguya geçirildi ve `category_minimums`
kaldırıldı; `python -m app.fetch --plan` dry-run çıktısı eklendi;
`venue_status_changed` operasyonel warning'i eklendi. Tüm değişiklikler
fixture'larla test edildi (33 test), `ruff check`/`format` ve migration
upgrade→downgrade→upgrade geçti; gerçek local DB'ye karşı `/health`, ana sayfa
ve venue kartı smoke testi yapıldı. Hiçbir gerçek API çağrısı yapılmadı.

Aynı gün, iki discovery filtresi (`min_user_ratings_total`,
`max_branches_per_brand`) kullanıcı isteğiyle gerçek ham aday havuzuna karşı
doğrulandı ve iki ürün kararı uygulandı: minimum review eşiği `100`→`50`, ve
brand şube sınırı tamamen kaldırıldı (aynı markanın tüm şubeleri artık ayrı
ayrı eklenebilir). `FilterResult.rejected_brand_cap` ve ilgili config/rapor
alanları koddan silindi. 33 test ve ruff kontrolleri geçti.

Push öncesi son bir review turunda kullanıcının 4 sorusu 2 gerçek bug/eksik
ortaya çıkardı ve düzeltildi: (1) `freshness_shortlist` adayları gerçek
freshness bilinmeden `target_count`'a daraltıyordu, bu yüzden freshness
sonucu hiçbir zaman seçimi değiştiremiyordu — artık hard filtreyi geçen tüm
adaylar freshness kontrolüne giriyor, daraltma yalnızca gerçek freshness
bilindikten sonra oluyor (regression testiyle kanıtlandı). (2)
`fetch --plan`, retry açıkken gerçek istek üst sınırını göstermiyordu —
`max_retries` ve `worst_case_http_requests_with_retries` alanları eklendi.
README.md discovery/fetch bölümleri de bugünkü tüm değişikliklerle güncellendi
(daha önce güncellenmemişti). 35 test, ruff check/format, `alembic check` ve
gerçek DB smoke testi geçti.

Son olarak, kullanıcı stability sinyaline "durgunluk" kavramını ekletti:
rating sayısı hâlâ artıyorsa mekan fresh sayılır, hem rating hem review
durursa süreye göre kademeli bir ceza uygulanır (60 gün ceza yok, 365 günde
tam ceza), mekan asla kataloğdan çıkarılmaz — yalnızca skor Bozdu yönüne
çekilir. Bu formül davranışı değiştiren bir tasarım kararı olduğu için yeni
bir score version — **`scoring.v5`** — açıldı (v4 frozen kaldı); aktif
`SCORING_CONFIG_PATH` hem `app/config.py` default'unda hem gerçek `.env`'de
`config/scoring.v5.toml`'a güncellendi. 37 test, ruff check/format,
`alembic check`, local recompute (30 venue v5'e taşındı) ve gerçek DB smoke
testi (API'de `score.version == "v5"`) geçti. Dormancy alanları şu an tüm
venue'larda gözlenemiyor çünkü stability henüz `insufficient_data` (tek
snapshot); birkaç hafta sonra gerçek etkisi görülecek.

## 2026-07-24 — Dormancy sınır durumu düzeltmesi + doküman senkronizasyonu

Kullanıcının işaret ettiği bir gerçek bug bulundu ve düzeltildi:
`_days_since_activity`, ne `user_ratings_total` artışı ne de review hiç
gözlenmemişse (tüm snapshot geçmişi boyunca tam sessizlik) `None` dönüyordu;
bu da `_dormancy_penalty`'nin cezasız (`0.0`) kalmasına yol açıyordu — yani en
uç durgunluk durumu (hiç kanıt yok) yanlışlıkla "kanıt yok, ceza yok" olarak
ele alınıyor, bir yıldır tamamen sessiz bir mekan `stable_high`+0.75 alarak
Coştu yönünde ödüllendirilebiliyordu. Düzeltme: aday tarih (growth/review)
yoksa en eski snapshot tarihi "son bilinen aktivite" referansı olarak
kullanılıyor artık (`app/scoring/engine.py`), yani tüm gözlem penceresi
boyunca hiç aktivite görülmemesi kademeli cezaya giriyor.
`test_never_active_venue_still_gets_dormancy_penalty` regresyon testiyle
kanıtlandı. Bu bir bugfix'tir (v5'in dokümante edilen niyetine karşı gerçek
bir implementasyon hatası), yeni score version açılmadı.

Ayrıca push öncesi bulunan doküman tutarsızlıkları giderildi: README'de iki
yerde "Aktif Scoring v4" / "Scoring v4 ... doğrulanır" ifadeleri unutulmuş,
`activeContext.md`'deki "Kesinleşen kararlar" bölümü hâlâ "aktif version
scoring.v4" diyordu, `techContext.md`'deki "Çalışma komutları" cheat-sheet'i
`--score-version v4` gösteriyordu — tümü v5'e güncellendi.

Son olarak, Faz 1/Task 2 ön koşulu olan "kataloğun 30'dan 40'a code
değişikliği olmadan çıkabildiğini doğrula" maddesi kullanıcı kararıyla Faz
1'i kapatmadan Faz 2 kapsamına taşındı (bkz. yukarıdaki "Faz 1 durumu" ve
`techContext.md`'nin "Faz 2'de netleştirilecek" bölümü); Faz 1 artık done.

## 2026-07-24 — Faz 2: Discovery genişletmesi (Eryaman + Batıkent)

Faz 2'nin ilk adımı olarak discovery mekanizması baştan tasarlandı ve
uygulandı. Önce plan modunda tam bir araştırma yapıldı: mevcut Text
Search (New) tabanlı akış detaylıca çıkarıldı (dahil: `included_type: null`
config değeriyle `SearchQueryState.included_type: str` arasındaki tip
uyuşmazlığının fresh bir `search --reset`'i çökerteceği, canlı koddan
doğrulanan gerçek bir bug), Google'ın Nearby Search (New)/Text Search
(New)/Places Aggregate API dokümantasyonu web'den araştırıldı ve üç karar
kullanıcıyla netleştirildi: (1) Eryaman + Batıkent iki ayrı, sıkı (~3km
yarıçaplı, merkezleri ~7.8km ayrık) bölge olarak modellenecek — tek
birleşik ~15km alan değil; (2) eski Text-Search tabanlı toplu keşif kodu
tamamen kaldırılacak, paralel bırakılmayacak; (3) webapp'te bölge gösterimi
bu adımın kapsamı dışı. Kullanıcı ayrıca kapsamı netleştirdi: yalnızca
restoran/kafe değil, Google Places API'nin "Food and Drink" Table A
kategorisindeki **tüm** tipler (~166 tip — bistro, pastane, dondurmacı,
tatlıcı ve tüm mutfak-spesifik `*_restaurant` tipleri dahil) taranacak.

Uygulama: `app/discovery/geo.py` (haversine + local tangent-plane offset),
`app/discovery/grid.py` (kare-grid + çevrel daire kapsama, tek-seviye
adaptif bölme, `chunk_types` ile 50'lik tip grupları), yeni
`app/adapters/places_nearby.py` (eski `places_new.py` silindi),
`app/discovery/search_cache.py`'nin hücre-tabanlı `discovery-search.v2`
şemasına yeniden yazımı, `discovery_stages.py`'nin `DiscoveryGridSearchStage`
ile yeniden yazımı, `selector.py`/`discovery_service.py`'nin
`select_candidates`/`target_count` yerine `accept_all_candidates`
(take-all) semantiğine geçirilmesi, `app/catalog.py`'ye bölgeler-arası
`place_id` çakışmasını önleyen `load_other_region_place_ids` eklenmesi,
`app/discover.py`/`app/fetch.py`'ye `--data-collection-config` bayrağı
eklenmesi. Google Places Aggregate API (`computeInsights`) araştırıldı:
gerçek bir ürün ama `INSIGHT_PLACES` modu yalnızca sayı ≤100 ise place_id
döndürüyor ve döndürdüğü tek şey place_id (metadata yok) — Nearby Search'e
göre net bir kazanç sağlamadığı için kullanılmadı.

Config dosyaları bölge başına ayrıştırıldı: `config/data_collection.eryaman.yaml`
+ yeni `config/data_collection.batikent.yaml` (merkez 39.968102, 32.726780 —
web'den doğrulandı), `config/catalog.eryaman.yaml` + yeni, boş
`config/catalog.batikent.yaml`. `app/config.py`'nin varsayılanları ve
`.env`/`.env.example` buna göre güncellendi.

51 test geçti (yeni: `test_discovery_grid.py`, `test_places_nearby_adapter.py`;
yeniden yazılan: `test_discovery.py`, `test_discovery_service.py`,
`test_discovery_stages.py`; silinen: `test_places_new_adapter.py`), ruff
check/format temiz, `alembic check` yeni migration göstermedi (şema
değişmedi — `Region`/`Venue` zaten coğrafi veri taşımıyordu, global
`uq_venue_provider_place_id` constraint'i zaten bölgeler-arası koruma için
hazırdı). Gerçek config dosyalarına karşı sıfır-maliyetli
`search --max-requests 0` dry-run'ı çalıştırıldı: her iki bölge de 276
arama birimi (69 coğrafi hücre × 4 tip grubu) üretti — bu sayı elle
(kare-grid geometrisiyle) hesaplanıp koddan gelen sonuçla birebir
doğrulandı. README ve memory-bank (techContext.md, dataModel.md,
activeContext.md) güncellendi. Henüz hiçbir gerçek Nearby Search veya
freshness API çağrısı yapılmadı; sıradaki adım onaylı dry-run → küçük prob
→ tam koşu aşamalarıdır (önce Eryaman'ın yeniden taranması, sonra Batıkent).

## 2026-07-24 — Eryaman'ın ilk gerçek search'ü + adaptif bölmenin kaldırılması

Kullanıcı onayıyla Eryaman'ın search aşaması gerçek API'ye karşı çalıştırıldı:
1 istekle smoke test, sonra 400 + 55 isteklik iki ek koşuyla tamamlandı.
Sonuç: **456 gerçek istek** (276 temel hücre×tip-grubu + 45 hücrenin tavana
çarpıp bölünmesinden gelen +180), 3359 ham aday, dedup+filtre sonrası **410
benzersiz yeni uygun mekan** freshness'a hazır (`search_completed: true`).

Kullanıcı bu +%65'lik öngörülemez artışı ("276 demiştin, 456 çıktı") kabul
edilemez buldu; "en az istekle en çok mekan bulmak, minimum duplication,
verimli altyapı" önceliğini netleştirdi ve sınır taşması gibi küçük
hassasiyet kayıplarının önemli olmadığını belirtti. Bunun üzerine **tek
seviyeli adaptif bölme mekanizması tamamen kaldırıldı**: tavana çarpan bir
hücre artık bölünmüyor, sonucu olduğu gibi kabul edilip yalnızca
`cells_flagged_for_review`'da işaretleniyor. Bu, bir bölgenin toplam arama
isteğini her zaman tam `hücre × tip-grubu` (Eryaman/Batıkent için 276) yapar
— dry-run'da görülen sayı artık kesindir, sürpriz büyüme olmaz. Bedeli: en
yoğun ceplerde (rankPreference=POPULARITY'nin en sona bıraktığı, genelde en
az review'lu) bazı mekanlar görülmeyebilir — kullanıcının önceliğiyle
uyumlu, bilinçli bir kabul.

Kod: `split_cell` (`app/discovery/grid.py`) silindi; `GridCellState.from_spec`
sadeleştirildi, `.spec()` kaldırıldı; `cells_flagged_for_review`,
`depth>=1` yerine `status=="searched" and hit_result_cap` olarak yeniden
tanımlandı. `depth`/`parent_cell_id` alanları ve `status="split"` değeri
yalnızca Eryaman'ın **zaten toplanmış ve ödenmiş** gerçek cache verisiyle
geriye dönük uyumluluk için şemada bırakıldı — bu kritikti, çünkü aksi
halde 456 gerçek isteğin sonucu kaybedilirdi. Değişiklik sonrası gerçek
Eryaman cache'i `app.discover status` ile tekrar okunup doğrulandı:
`cells_flagged_for_review` yeniden tanım öncesi/sonrası aynı sonucu (19)
verdi, `freshness_required` hâlâ 410 — hiçbir veri kaybı yok. 50 test
geçti (2 bölme testi silindi; 1 yeni "bölünmeden kabul et" davranış testi
+ 1 yeni geriye-dönük-uyumluluk testi eklendi), ruff check/format temiz.

Freshness aşaması (410 istek) henüz başlatılmadı; kullanıcı onayı
bekleniyor. Onaylanınca sıradaki adım `freshness --max-requests N` →
`finalize`, sonra aynı akışla Batıkent.

## 2026-07-24 — Eryaman freshness + finalize + excluded_primary_types filtresi

Kullanıcı onayıyla 410 mekan için freshness çalıştırıldı: **410/410
başarılı, 0 hata.** Sonuç: 405 fresh, 5 stale (en eskisi Göktuğ
Kavurma&Izgara, son review 2025-02-06), **0 mekan hiç review'suz**;
medyan son-review-yaşı 5 gün, %88'i son 30 gün içinde review almış — bulunan
mekanlar genel olarak aktif. Ardından `finalize` (local, ücretsiz)
çalıştırıldı: 410 eklendi, 30 korundu, katalog 440 oldu.

Kategori dağılımı incelenirken (kullanıcı isteğiyle "sonuçları
değerlendirelim") yemekle ilgisiz 11 kategori bulundu — isimlerine
bakıldı: `medical_clinic` (bir diyetisyen/fizyoterapi kliniği),
`barber_shop`, `hair_salon`, `supermarket` (Bim), `store` (nargile
dükkanı), `swimming_pool`, `amusement_center` (çocuk oyun evi),
`video_arcade` (simülasyon merkezi) — bu 8'i açıkça alakasız; ayrıca 3
sınırda kalan (`sports_complex`="...Pool Cafe", `garden_center`="Ankara
Barbekü", `wedding_venue`) isimlerinde yemek/ikram ima ediyordu. Kök
neden: Nearby Search'ün `includedTypes`'ı (Google'ın kendi FAQ'sinde
belgelendiği gibi) bir mekanın TÜM tip etiketlerine bakar, yalnızca
`primaryType`'a değil — `includedPrimaryTypes` kullanılsaydı bu sızıntı
olmazdı ama gerçek food/drink mekanlarını (primary type'ı farklı olanları)
kaçırma riski vardı, bu yüzden bilinçli olarak `includedTypes` seçilmişti.

Kullanıcı kararı: 8 açıkça alakasız kategoriyi kaldır, 3 sınırdakini tut;
bundan sonra bu tip mekanlar için gereksiz freshness çağrısı atılmasın.
Uygulama: yeni `excluded_primary_types` config alanı (`DiscoveryConfig`) +
`apply_hard_filters`'a `rejected_irrelevant_primary_type` reddi eklendi —
freshness'tan **önce** çalışır (`_filtered_candidates` içinde). İki config
dosyasına da (Eryaman + Batıkent) aynı 8 kategorilik dışlama listesi
eklendi. Zaten kataloğa girmiş 8 mekan `config/catalog.eryaman.yaml`'dan
elle çıkarıldı (440→432).

Operasyonel not: config/katalog dosyaları değiştiği için discovery
cache'inin kayıtlı `collection_config_hash`/`catalog_hash`'i artık
uyuşmuyordu (`--reset` istendi) — **`--reset` kullanılmadı** (456+410
gerçek/ödenmiş isteği silerdi); bunun yerine cache'in saklı hash'leri yeni
dosyaların gerçek hash'ine elle güncellendi (bu değişikliğin arama
sonuçlarını geçersiz kılmadığı, yalnızca sonraki local filtrelemeyi
etkilediği bilinerek). `finalize` yeniden çalıştırıldı (local, ücretsiz):
katalog 432'de sabit kaldı; `apply_hard_filters` bu 8 place_id'ye karşı
ayrıca doğrudan test edilip `rejected_irrelevant_primary_type=8` verdiği
kanıtlandı — hiçbir veri kaybı, hiçbir yeni API çağrısı olmadı. 51 test
geçti, ruff check/format ve `alembic check` temiz.

**Eryaman durumu: 432 mekan kataloğa girdi, henüz DB'ye sync edilmedi**
(bir sonraki `app.fetch` koşusunda `sync_catalog` ile olacak, aynı anda bu
402 yeni mekan için "snapshot 1" üretilecek). Sıradaki adım: `app.fetch
--region eryaman` (gerçek snapshot) veya Batıkent'in aynı akışla
başlatılması — ikisi de kullanıcı onayı bekliyor.

## 2026-07-25 — Takip edilen mekan (tracked) seçimi + iki haftalık cadence

432 mekanlık Eryaman kataloğunun tamamını 2 haftada bir Legacy Detail ile
izlemek gereksiz maliyetli olacağından, kullanıcı dinamik bir top-N
mekanizması istedi: `user_ratings_total`'a göre en popüler
`tracked_venue_limit` (`200`) kadarı aktif izlensin, geri kalanı kataloğda
kalsın ama fetch edilmesin — ve bu seçim **sabit değil**, her aylık
`finalize`'da yeniden hesaplansın (review sayısı büyüyen bir mekan tekrar
top-N'e girebilsin). Aynı oturumda birleşen iki ek karar: fetch cadence'i
`weekly`'den `biweekly`'e düşürüldü; Legacy fetch tek sort'a (`newest`)
indirildi. İkincisinin gerekçesi kod üzerinden doğrulandı: `rating`/
`price_level` zaten sort'tan bağımsız `fields` parametresiyle geliyor,
`rating_trajectory`/`stability`/`review_velocity` sinyalleri `newest` +
review sayısı artışıyla tam besleniyor, yalnızca `sentiment_keyword_drift`
`most_relevant`'a ufak/kontrolsüz bir bağımlılık taşıyor — Google'ın
`most_relevant` sonuçlarının tarih/sıra garantisi olmadığından bu katkı
zaten güvenilmezdi. Açık kalan bir soru ("yeni keşfedilen mekanlara koruma/
grace-period gerekir mi?") kullanıcıya soruldu; cevap **hayır, yalnızca
review sayısı** oldu — Google Places API açılış tarihi vermediğinden
güvenilir bir "ne kadar yeni" sinyali zaten yok.

Uygulama: yeni migration `0004_add_venue_is_tracked` (`venues.is_tracked`,
`default=true`, `0003`'ün devamı); `DiscoveryConfig.tracked_venue_limit`
(`200`), `FetchConfig.cadence_anchor_date` (her bölge için
`2026-07-13`, bir Pazartesi) eklendi, `FetchConfig.review_sorts` validator'ü
`{"newest"}`'e daraltıldı; `app/cadence.py`'nin `period_start_for`'ına
`anchor_date` parametreli biweekly hesaplama eklendi (hafta farkının
tekliği periyodu bir hafta geri kaydırır); `app/discovery/selector.py`'ye
saf `rank_tracked_venues` fonksiyonu eklendi (veri yokken dokunmama, eşitte
`place_id` tie-break); `VenueCatalogEntry`'ye `tracked`/`user_ratings_total`
alanları eklendi; `build_discovery_result`/`_run_finalize` yeni
`all_scanned_candidates` parametresiyle her `finalize`'da yeniden sıralama
yapacak şekilde entegre edildi; `app/fetch.py`/`FetchService.run` artık
yalnızca `is_active AND is_tracked` venue'ları işliyor (`is_active` ile aynı
iki-katmanlı katalog→DB deseni, `sync_catalog` üzerinden).

Kod okurken gerçek bir bug bulundu ve düzeltildi (implementasyona
başlamadan önce, plan aşamasında tespit edildi): freshness'ın seed'lediği
`newest` payload'u yalnızca `fields=reviews` ile alındığından `name`
içermiyor; eski `reusable` filtresi bunu sort eşleşmesine bakıp (state
içerip içermediğine bakmadan) yine de "kullanılabilir" sayıyordu. Dual-sort
rejiminde zararsızdı (state her zaman taze `most_relevant`'tan geliyordu)
ama tek-sort rejiminde hiç HTTP isteği yapmadan `fetch_place`'in
`PlacesApiError("...contains no venue state")` ile çökmesine yol açardı.
Düzeltme: `app/adapters/places_legacy.py`'deki `reusable`, yalnızca
`result.name` içeren payload'ları seed kabul edecek şekilde daraltıldı.

Doğrulama: 24 yeni test (toplam 75 geçiyor) — `rank_tracked_venues` (limit
üstü/altı, veri yokken dokunmama, incumbent'ın düşürülebilmesi), biweekly
`period_start_for` (anchor'a göre doğru period, negatif offset, anchor'sız
`ValueError`), seed-safety bugfix regresyonu, `is_tracked` katalog/DB
round-trip, `FetchConfig` validator'leri (`review_sorts`, `cadence_anchor_date`),
`finalize`'ın `tracked_count`/yeniden sıralama entegrasyonu, `FetchService`'in
`is_tracked` filtresi. `ruff check`/`format` temiz. `0004_add_venue_is_tracked`
migration'ı önce **scratch bir DB'de** upgrade→downgrade→upgrade→`alembic
check` ile doğrulandı (gerçek DB'ye o an henüz dokunulmadı — bilerek,
gerçek DB değişikliği ayrı bir onay bekliyordu; bkz. aşağıdaki paragraf,
o onay aynı gün geldi). README ve memory-bank (techContext.md,
dataModel.md, activeContext.md) güncellendi.

**Gerçek veriye uygulama (aynı gün, kullanıcı onayıyla tamamlandı):**
migration önce yedek alınarak gerçek local `data/ora_bozdu.db`'ye
uygulandı (`alembic upgrade head`, `alembic check` temiz, mevcut 47 DB
venue'su doğru `is_tracked=true` aldı). Eryaman için `finalize` **mevcut,
zaten toplanmış cache ile** (yeni API çağrısı yok) yeniden çalıştırıldı;
config bu oturumda değiştiği için cache'in `collection_config_hash`'i
(daha önceki `excluded_primary_types` düzeltmesinde kullanılan aynı
teknikle, `--reset` kullanmadan) elle güncellendi. **Sonuç: 432 mekanlık
kataloğun 200'ü `tracked`, 232'si değil** — en yüksek review'lu tracked
mekan "ANZELHA ERYAMAN" (14164 review), kesim noktası ~205 review
civarında temiz (son tracked ~205-206, ilk not-tracked 192-203). Katalog
dosyası gerçekten yeniden yazıldı; DB'nin `is_tracked` kolonu bir sonraki
gerçek `app.fetch` koşusunda `sync_catalog` ile senkronlanacak.

**İlk gerçek biweekly fetch (aynı gün, onaylandı ve tamamlandı):** önce
`--plan` ile önizleme onaylandı (200 mekan, 200 istek, `--no-retries` ile
kesin üst sınır), ardından gerçek koşu onaylandı.
`app.fetch --region eryaman --no-retries` **200/200 başarılı, 0 hata, 0
warning**. `sync_catalog` DB'yi kataloğa senkronladı: DB'de
`is_active AND is_tracked` tam **200**, `is_active AND NOT is_tracked` tam
**232** (katalogla birebir; ayrıca güncel katalogda olmayan 17 eski/pasif
venue DB'de zararsız kalıntı olarak duruyor). 200 yeni `biweekly`
snapshot'ı tek `newest` payload'ıyla yazıldı. Örnek gerçek veri: "ANZELHA
ERYAMAN" 4.4★/14164 review, "Köfteci Yusuf" 3.7★/9582 review — finalize
raporundaki sayılarla neredeyse birebir. Sıradaki adım için bkz. aşağıdaki
bölge-değişikliği kaydı (ikinci bölge Batıkent yerine artık Armada).

## 2026-07-25 — Webapp: konum linki, veri güveni popup'ı, Nearby Search SKU doğrulaması

Kullanıcı isteğiyle venue kartına `provider_place_id`'den üretilen bir
Google Haritalar linki ve "Veri güveni" piline tıklanınca açılan, aktif
`scoring.v5.toml`'dan dinamik değerler kullanan bir açıklama popup'ı
eklendi. Statik varlıklara (`app.css`/`app.js`) içerik-hash'li bir cache
buster eklendi — bir tarayıcının eski JS'i önbelleklemesi yüzünden
"tıklanmıyor" raporu alındıktan sonra kalıcı çözüm olarak.

Ayrıca kullanıcının "Google Cloud Console'dan fiyatı kontrol edelim"
isteği üzerine Nearby Search'ün gerçek SKU'su Google'ın resmi
dokümantasyonundan doğrulandı: field mask'imiz Enterprise SKU'yu
tetikliyor ($35/1.000 istek, 1.000/ay ücretsiz). Bu araştırma sırasında
kod okuması gerçek bir tasarım boşluğu ortaya çıkardı: `finalize` DB'ye
hiç bağlanmadığı ve `search`'ün cache'i tamamlandıktan sonra kendiliğinden
yenilenmediği için, `--reset` kullanılmadan çalıştırılan bir aylık
discover ne yeni mekan bulabiliyor ne de takip sıralamasını gerçekten
güncelliyor (sıralama hep ilk tarama anındaki donuk sayılarla kalıyor).
Kullanıcı kararı: aylık discover akışı artık zorunlu olarak
`search --reset` ile başlayacak — SKU hesabına göre bu maliyetsiz (iki
bölgenin tam taraması ~732 istek, 1.000 ücretsiz kotanın altında). Kod
değişikliği gerekmedi; `all_scanned_candidates` mekanizması bu senaryoyu
zaten doğru destekleyecek şekilde tasarlanmıştı. README ("Bir kerelik
discovery" → "Discovery (aylık, `--reset` ile tekrarlanır)") ve
techContext.md güncellendi.

## 2026-07-25 — İkinci bölge değişikliği: Batıkent → Armada

Kullanıcı ikinci bölge olarak Batıkent'i iptal edip yerine **Armada**
(Söğütözü, `39.911640, 32.809945`) koydu, yine `r=3km`. Batıkent'te hiç
gerçek API çağrısı yapılmamıştı (katalog boştu), bu yüzden placeholder
`config/catalog.batikent.yaml` + `config/data_collection.batikent.yaml`
git'ten silindi ve aynı şablondan `config/*.armada.yaml` üretildi
(yalnızca `region` ve `brand_stopwords` bölgeye özel; 166 tip, filtreler,
`tracked_venue_limit=200`, biweekly cadence Eryaman'la birebir).

"r=3km mantıklı mı?" sorusuna: WebSearch ile Söğütözü'nün gerçek bir
yeme-içme yoğunluğu (56+ kafe, iş merkezi + sosyal yaşam kesişimi) olduğu
doğrulandı — salt ofis/otoyol koridoru değil. Zero-cost
`search --max-requests 0 --reset` dry-run'ı **276 hücre** verdi (Eryaman'la
birebir; sayı salt grid geometrisinden geliyor, konumdan bağımsız).
Eryaman-Armada merkez mesafesi `app/discovery/geo.py`'nin `distance_meters`'ı
ile **~16,6km** — bölgeler arası koruma normalde tetiklenmez.

`test_fetch_cli.py`'deki per-region config testi batikent→armada
güncellendi; README ve tüm memory-bank dosyaları Batıkent→Armada geçişiyle
tazelendi (2026-07-24 tarihli tarihsel narrative kayıtları, o gün Batıkent
gerçekten plandaki bölge olduğu için değiştirilmedi — yalnızca güncel-durum
ve sonraki-adım ifadeleri güncellendi). 77 test + ruff temiz. Henüz hiçbir
gerçek Armada API çağrısı yapılmadı; sıradaki adım onaylı dry-run →
smoke → tam koşu (Eryaman'da izlenen akışın aynısı).

## 2026-07-25 — Faz 3: Review backfill (harici scraper) + Scoring v6

Places API fetch başına ~5 review veriyor ve agregat rating popüler mekanlarda
atıl olduğundan `sentiment_keyword_drift` (gürültü) ve `rating_trajectory`
(yavaş + atıl) zayıf. Kullanıcı harici bir Google Reviews scraper'ıyla her
tracked mekanın son 12 ayının newest review'larını çekmek istedi. Uzun bir
netleştirme turu: scraper (`google-reviews-scraper-pro`, MIT, SeleniumBase UC)
incelendi, ToS/risk dürüstçe konuşuldu (local + ticari değil = en düşük risk),
ve kritik teknik nokta düzeltildi — scraping mevcut `stability`'yi (agregat
volatilitesi, snapshot'lardan) beslemez; asıl kazanç sentiment (50× veri) ve
**review-window rating trajesi** (kayan-pencere yıldız ortalaması, agregatın
gizlediği düşüşü yakalar). Mimari ilke: mutlak seviye API'de (ground-truth),
scraper yalnızca trend/geçmiş/sentiment; `source=backfill` ile ayrı. Filtre:
son 12 ay + `max_reviews: 200`.

Plan onaylı, tamamlandı: migration `0005_add_venue_reviews` (`venue_reviews`
tablosu, venue'ya bağlı corpus); `app/backfill.py` iki komut —
`generate-config` (tracked katalogdan scraper businesses YAML'ı, her mekan
`custom_params.ora_bozdu_slug` ile; scraper place_id'si `ChIJ...` olmadığından
join slug üzerinden — scraper'ın `CustomParamsTask`'inin JSON'a slug'ı eklediği
kod okumasıyla doğrulandı) ve `import` (JSON → idempotent upsert,
`description: {lang:text}` birleştirilir); Scoring v6 — engine `ReviewInput`
Protocol'ü (SnapshotReview + VenueReview ortak), `rating_trajectory`
review_window modu (corpus varsa; yoksa agregat fallback, `details.mode`),
`compute_venue_score` corpus-preference (`_reviews_for_scoring`);
`scoring.v6.toml` + aktif version v6 (v5 frozen, review_window kapalı default).
Scraper HARİCİ kalır (heavy deps repoya girmez). 88 test (10 yeni), ruff temiz,
migration scratch DB'de upgrade→downgrade→upgrade→`alembic check` temiz. Canlı
sanity: flat 4.3 agregat + son review 5→2 yıldız → v6 review_window yakalıyor,
**bozdu** (v5 kaçırırdı).

Adım 8-A yapıldı (kullanıcı onayıyla): migration gerçek DB'ye uygulandı,
v6 recompute (206 mekan; corpus yokken agregat fallback = webapp v6'da çalışır),
scraper config üretildi.

## 2026-07-25 — Backfill aracı değişti: google-reviews-scraper-pro → Outscraper API

google-reviews-scraper-pro gerçek ortamda denendi: onay + kurulum (ayrı venv,
seleniumbase/boto3), tek-mekan smoke başarılı (MRADA CAFE 30 review, 44 sn,
slug-join + import çalıştı). Ama 200-mekan tam koşusu ~3-5 saat (mekan başına
~25-30 sn'si sadece browser navigasyonu, API değil tarayıcı otomasyonu olduğu
için) + anti-detection kırılganlığı olduğundan kullanıcı bu aracı bıraktı ve
**Outscraper Google Maps Reviews API**'sine geçti.

Temizlik: klon + scraper venv + smoke artefaktları silindi; smoke'ta gerçek
DB'ye giren 30 `venue_reviews` satırı temizlendi (0). Yeniden mimari (kullanıcı
"aracımız API'yi doğrudan çağırsın" seçti): `pyproject`'e `outscraper` dep
(lazy import — modül/testler onsuz çalışır), `OUTSCRAPER_API_KEY` Settings/`.env`;
`app/backfill.py` baştan yazıldı:
- `fetch` — Outscraper SDK'sını tracked place_id'lerle (25'lik gruplar) çağırır
  (`reviews_limit=100 sort=newest cutoff=12ay language=tr`), ham yanıtı
  `data/outscraper-<region>.json`'a persist'ten önce yazar, sonra import eder.
- `fetch --plan` — maliyet-şeffaf ön izleme (mekan/API-çağrısı/tahmini-review/
  cost-note), API çağırmaz.
- `import --input` — kayıtlı Outscraper JSON'u alır.
**place_id join temizlendi:** Outscraper `ChIJ...` döndürdüğünden doğrudan
`provider_place_id` join; eski slug/custom-param köprüsü + `generate-config`
kaldırıldı. Testler Outscraper formatına yeniden yazıldı (API çağırmadan),
**90 test geçiyor**, ruff temiz. `venue_reviews` + Scoring v6 (review-window)
dokunulmadan duruyor.

**Güvenlik olayı:** bir `grep` `.env`'deki gerçek `GOOGLE_MAPS_API_KEY`'i
terminale bastı; kullanıcıya rotate bildirildi (bkz. feedback belleği). Bundan
sonra `.env`'e hassas grep yok.

**Henüz yapılmadı (Outscraper 6, onay + key bekliyor):** gerçek `app.backfill
fetch --region eryaman` (paralı) → v6 recompute → raporla.

## 2026-07-25 — Backfill aracı değişti: Outscraper → Apify (maliyet)

Outscraper'ın gerçek `fetch`'i hiç koşulmadan, fiyatı (mekan başı 100 review →
üst sınır ~$58.5) pahalı bulundu; kullanıcı **Apify Google Maps Reviews Scraper**
actor'üne (`compass/google-maps-reviews-scraper`) geçti ve mekan başı review'u
**100 → 50**'ye çekti (sentiment + 12-ay trajesi için yeterli).

`app/backfill.py` Apify'a göre baştan yazıldı:
- `fetch` — tüm tracked place_id'leri **tek Apify run**'ında çalıştırır
  (`client.actor(...).call(run_input={placeIds, maxReviews=50,
  reviewsSort='newest', reviewsStartDate='365 days', language='tr',
  reviewsOrigin='all', personalData=True})`), dataset'i iterate eder, ham yanıtı
  `data/apify-<region>.json`'a persist'ten önce yazar. Batch'leme kalktı (Apify
  kuyruğu içeride yönetiyor).
- `persist_reviews` (eski `persist_places`) artık Apify'ın **düz review-item**
  listesini alır (her item `placeId` taşır) — Outscraper'ın nested `reviews_data`
  yapısı yerine. Parse: `publishedAtDate` (ISO), `stars`, `text`, `name`,
  `reviewId`. `placeId` → `provider_place_id` join, `(venue_id, dedup_key)`
  idempotent upsert korundu.
- `fetch --plan` fiyatı Apify'a göre (~$0.30/1000, pay-per-event): 200 × 50 =
  10.000 review → **üst sınır $3** (Apify'ın aylık $5 ücretsiz kredisi
  karşılayabilir → potansiyel $0).

Config/dep: `OUTSCRAPER_API_KEY` → `APIFY_TOKEN` (Settings `SecretStr`, `.env`
sessiz `sed` ile — secret bastırılmadı), `pyproject` `outscraper` → `apify-client`
(lazy import). `.gitignore` `data/outscraper-*` → `data/apify-*`. Testler Apify
formatına yeniden yazıldı (actor çağırmadan). Dokümanlar (README/techContext/
dataModel) Apify'a güncellendi. `venue_reviews` + Scoring v6 dokunulmadı.

**Henüz yapılmadı (onay + `APIFY_TOKEN` bekliyor):** gerçek `app.backfill fetch
--region eryaman` (paralı, ~$3 üst sınır) → v6 recompute → raporla. `uv.lock`
Apify dep için henüz pin'lenmedi (uv PATH'te yok).

## 2026-07-25 — Apify birleşik pipeline: Place Details fetch supersede

Kullanıcı token'ı ekledi + iki karar: **(1)** `reviewDetailedRating → sub_ratings`
eklendi (kategori Food/Service/Atmosphere; reviewer doldurmadıysa `{}` → None).
**(2)** `apify-client` 3.1.0 kuruldu (`.venv` pip; `pyproject` pin `>=3.0`), SDK
yüzeyi (`actor().call()` + `dataset().iterate_items()`) ağsız doğrulandı.

**Büyük mimari değişiklik:** Apify her review item'ında mekan agregatını
(`totalScore`→rating, `reviewsCount`→user_ratings_total, `title`→name) da verdiği
için **paralı Google Place Details `fetch`'i supersede edildi**. `app/backfill.py`'ye
`persist_snapshots` eklendi: Apify agregatından `place_snapshots` üretir
(`FetchRun(provider="apify")`, `(venue,cadence,period_start)` idempotent,
name-change WARNING). `fetch` artık **tek koşuda** `persist_reviews` (corpus) +
`persist_snapshots` (agregat) + `recompute_region` (v6) çalıştırır; cadence/period
`data_collection.<region>.yaml`'dan gelir (CLI `--data-collection-config`/`--date`
eklendi).

Kararlar (kullanıcı, AskUserQuestion): business_status kaybı → **dormancy yeter**
(ekstra Google çağrısı yok; Apify snapshot'larında business_status/price_level
NULL); **şimdi birleşik kur** (throwaway koşu yok). Discover hâlâ Google Nearby
Search'te ("sadece discover dursun; sonra onu da scraper'a bakarız"). Scoring kodu
**hiç değişmedi** — zaten `place_snapshots` + `venue_reviews` corpus'undan besleniyor.

Doğrulama: **98 test** (4 yeni snapshot testi), ruff temiz. `fetch --plan` gerçek
katalogda: 200 mekan, biweekly period 2026-07-13, 10k max review, **$3 üst sınır**,
`produces: place_snapshots + venue_reviews + v6 recompute`. Dokümanlar (README/
techContext/dataModel) güncellendi; `app.fetch` supersede notlarıyla korundu.

**Henüz yapılmadı (onay bekliyor):** gerçek `app.backfill fetch --region eryaman`
(paralı ~$3). `uv.lock` Apify dep için pin'lenmeli (uv PATH'te yok).

## 2026-07-26 — Apify gerçek koşu + v6 count-split/review-consistency + aylık plan

**Apify gerçek koşusu yapıldı** (onaylı; ~$5 = Apify aylık ücretsiz kredisi doldu):
200 tracked mekan, **8336 review** → `venue_reviews` corpus (181 mekan; 19'u
pencerede review döndürmedi), 0 unmatched, sub_ratings ~%100. Snapshot'lar bu
periyodu (2026-07-13) Google zaten tuttuğundan skip edildi; v6 recompute 206 mekan.
Küçük canlı smoke (3 mekan) alan şekillerini doğruladı ve **apify-client 3.x'te
`.call()` dict değil `Run` nesnesi döndürüyor** bug'ını yakaladı →
`run.default_dataset_id` düzeltmesi.

**v6 evriltildi (kullanıcı yönlendirmesi — takvim penceresi yanlıştı):**
- `rating_trajectory` **review_window → count-split**: 50 review takvime
  sıkıştırılmıyor; tarihe göre sıralanıp newest yarı vs older yarı (sayıya göre)
  karşılaştırılıyor. Yoğun mekan (Halimbey 50 review = 69 gün) da çalışıyor.
- `stability` **review-consistency eklendi**: 50 review 5 zaman-bucket'ı, bucket
  ortalamalarının stddev'i → seviye oynaklığı. Snapshot beklemeden `available` →
  `early_phase_cap` (0.45) kalkıyor.
- **volatile eşik kalibrasyonu 0.40→0.65:** ilk recompute'ta 109 mekan volatile
  çıktı; sebep 10'luk bucket integer-rating gürültü tabanının (~0.38) eşiğe denk
  gelmesi. 0.65'e çekince 56 (gerçek savrulanlar; Arabica/IL FORNO stable'a döndü).

**Sonuç (Halimbey):** trajectory kanıt gücü %1→%100, veri güveni %35→%84,
stability insufficient_data→stable_low. Bölge geneli: confidence ort 0.45→0.73,
177/206 mekan >%45; **88 dengede / 70 coştu / 48 bozdu**. **102 test**, ruff temiz.

**Operasyonel plan (kullanıcı):** bundan sonra discover + Apify snapshot **ayda
bir** elle. Yavaş genişleme; **sıradaki task: Armada** bölgesi. Not: `cadence`
config `biweekly`; aylık period bucket için `period_start_for`'a "monthly"
eklemesi gerekir (Armada'yla değerlendirilecek). Versiyon: v6 evriltildi
(yayınlanmamıştı; istenirse v7).
