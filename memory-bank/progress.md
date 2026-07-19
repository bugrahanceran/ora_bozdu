# İlerleme

## Genel durum

Phase 1 / Task 1'in ilk implementation doğrulamaları geçti. Nihai veri toplama
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
- [ ] İlk katalog koşusundan sonra discovery'yi tek birleşik cafe/restoran
      sorgusuna geçir ve category minimum kotalarını kaldır.
- [x] Config-driven minimum uygun aday havuzuna ulaşınca pagination'ı erken
      bitir; mevcut search'i üçüncü restaurant sayfasını çekmeden tamamla.
- [x] Ayrı kullanıcı onayıyla ilk official haftalık snapshot fetch'ini tamamla
      (30/30 snapshot, 60/60 HTTP response başarılı, retry yok).
- [x] HTTP client INFO loglarında API key içeren request URL'lerini bastır;
      kullanıcıya açığa çıkan key'i rotate etmesini bildir.

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

## Task 2 hazırlığı

- [ ] Venue kataloğunun 30'dan 40 kayda code değişikliği olmadan çıkabildiğini
      Task 1 sonunda doğrula.

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
