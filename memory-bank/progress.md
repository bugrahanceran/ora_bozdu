# İlerleme

## Genel durum

Phase 1 tamamlandı (2026-07-24). Task 1'in tüm checklist maddeleri ve push
öncesi son review'da bulunan düzeltmeler geçti. Nihai veri toplama
kararıyla otomatik discovery, YAML catalog ve cadence-aware haftalık fetch
dönüşümü açıldı. `GOOGLE_MAPS_API_KEY` yapılandırılmıştır fakat kullanıcı onayı
olmadan hiçbir ücretli API koşusu yapılmaz. Önceden terminal çıktısında görünmüş
olan key kullanıcı tarafından rotate edilmiştir; güncel key yalnızca `.env`
içindedir.

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
