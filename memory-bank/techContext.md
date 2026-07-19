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
- Idempotency cadence-aware olur. Başlangıç cadence'i haftalıktır; aynı venue,
  hafta ve review sıralaması yeniden çalıştırıldığında duplicate üretilmez.
  Cadence config ile `daily` yapılabilir. Eksik/başarısız venue'lar güvenli
  biçimde tekrar denenebilir.
- Bir venue için iki zorunlu review-sort response'u önce memory'de toplanır;
  snapshot, raw payload, review ve appearance kayıtları ancak ikisi de başarılı
  olduğunda tek DB transaction'ında yazılır. Yarım snapshot commit edilmez.
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

## Discovery — Places API (New) Text Search

Venue seçimi `python -m app.discover` ile, webapp ve periyodik fetch'ten ayrı bir
adım olarak yapılır:

- Devam eden ilk live discovery'de `restaurant` ve `cafe` için ayrı Text Search
  (New) sorguları çalışır; cafe sorgusu checkpoint edildiği için bu koşunun
  request planı değiştirilmez.
- Ürün kararı gereği cafe/restoran dağılım kotası gerekli değildir. İlk katalog
  koşusundan sonraki discovery yenilemesinde iki türü kapsayan tek genel Text
  Search sorgusu kullanılacak, category minimum kotaları uygulanmayacaktır.
- Arama Eryaman Metromall merkezli yaklaşık `39.979, 32.636` koordinatı ve
  config'teki `2000` metre çemberle sınırlandırılır.
- Text Search (New), circle biçimini `locationBias` için kabul ederken
  `locationRestriction` için yalnızca rectangular viewport kabul eder. Bu
  nedenle config-driven merkez/radius'tan çemberi kapsayan rectangle hesaplanıp
  API restriction olarak gönderilir; dönen koordinatlara ayrıca local haversine
  filtresi uygulanır. Bu iki adım birlikte 2 km dışındaki viewport köşelerini
  eler ve radius'u gevşek bir bias'a dönüştürmez.
- Sayfalama, `nextPageToken` bitene veya hard filter + brand cap sonrasında
  kalan benzersiz aday sayısı config'teki `minimum_candidate_pool` eşiğine
  ulaşana kadar sürer. Başlangıç eşiği 30'dur; hedef sayı daha yüksekse hedef
  sayı alt sınır olur. Category minimumları bulunan geçiş config'inde erken
  durma için bu minimumların da karşılanması gerekir. Google'ın mevcut Text
  Search (New) sınırı sorgu başına toplam 60 sonuçtur.
- Discovery field mask yorumsuz ve minimaldir: place ID, display name,
  business status, user rating count, type ve local radius filtresi için
  location bilgisi.
- Local hard filter başlangıçta `OPERATIONAL`, minimum 100 rating ve aynı
  brand'den en fazla iki şubedir. Eşiklerin tamamı config'tedir.
- Hard filter sonrasında kalan kısa liste, Legacy Place Details
  `reviews_sort=newest` çağrısıyla en yeni review tarihi açısından kontrol
  edilir.
- Task 1 katalog hedefi 30 venue'dur. Uygun havuz hedefi aşarsa freshness
  öncesinde `log(user_ratings_total)` tabanlı preliminary ranking, category
  minimumları ve place ID tie-break ile tam hedef büyüklüğünde deterministik
  shortlist oluşturulur. Bu nedenle mevcut 31 uygun adaydan 30'u Legacy
  freshness kontrolüne girer.
- Deterministik seçim skoru `log(user_ratings_total)` ile config'teki freshness
  cezasını birleştirir. Altı ay veya daha uzun süredir sessiz venue ceza alır.
  Eşitlik `place_id` alfabetik sırasıyla bozulur.
- Mevcut ilk koşunun geçici config'i en az 6 cafe ve en az 10 restoran kotası
  taşır. Bu kota yalnızca checkpoint edilmiş koşuyu tutarlı tamamlamak içindir;
  sonraki discovery sürümünde kaldırılacaktır. Hedef venue sayısı ve diğer
  eşikler config'te kalır.
- Çıktı `config/catalog.yaml` ve aday/eleme/seçim sayılarını içeren kısa bir
  rapordur. `--target-count N` mevcut katalog kayıtlarını koruyarak yalnızca
  yeni venue ekler; mevcut venue otomatik çıkarılmaz.
- Discovery seçimi otomatiktir. Proje sahibi seçim raporunu denetler fakat
  normal akışta manuel venue seçimi yapılmaz.
- Ücret kontrolü için discovery staged çalışır: `search`, `freshness`,
  `finalize`. Her `search`/`freshness` koşusu `--max-requests` ile logical çağrı
  bütçesi alır; `--no-retries` tek HTTP denemesi garantisi için kullanılır.
- Her live koşu öncesi onay mesajı komutu ve azami HTTP istek sayısını içerir.
  Pricing ilk seferde referans olarak doğrulanmıştır; kullanıcı istemedikçe
  sonraki onaylarda fiyat tekrarlanmaz.
- Aynı açık onay kapsamındaki bounded çoklu istek için venue başına tekrar onay
  alınmaz. Güncel freshness koşusu tek CLI çalıştırmasında azami 30 Legacy Place
  Details isteği olarak sunulur; `--no-retries` bu üst sınırın aşılmamasını
  sağlar.
- İlk live discovery freshness koşusu 2026-07-19 tarihinde 30/30 başarılı
  Legacy newest-review isteğiyle tamamlandı. O koşudaki ilk implementation
  yalnızca seçim için en yeni review tarihini cache'e yazdı; append-only DB
  snapshot üretmedi.
- Bu ilk live koşudan sonra bootstrap tekrarını önlemek için freshness cache
  şeması ham `details_newest` payload, fetched timestamp ve payload hash'i de
  saklayacak şekilde genişletildi. Aynı `as_of_date` ile yapılan ilk fetch bu
  payload'u provider'a seed eder; adapter yalnızca eksik review sort'u çağırır,
  state'i tam-field payload'dan parse eder ve iki payload'u tek atomik snapshot
  bundle'ında birleştirir. Eski cache'te ham response bulunmadığı için bu
  optimizasyon ilk 30 venue'luk live koşuya geriye dönük uygulanamaz.
- Her live run öncesi onay ekranında endpoint bazlı istek adedi, toplam ve retry
  durumu görsel olarak özetlenir. Pricing hesabı rutin onay akışının parçası
  değildir; yalnızca kullanıcı ayrıca isterse yeniden gösterilir.
- Search sayfaları, page token'ları ve normalize adaylar
  `data/discovery-search-cache.json` içinde checkpoint edilir. Search tamamen
  bitince local hard filter uygulanır ve freshness için gereken kesin Legacy
  istek sayısı kullanıcı onayına sunulur. `finalize` ağ çağrısı yapmaz.
- Erken tamamlanan cache `completion_reason=minimum_candidate_pool` taşır;
  tüketilmeyen `nextPageToken` korunur. `search --max-requests 0` mevcut cache'i
  yalnızca local kuralla uzlaştırır ve provider/API çağrısı yapmaz.
- 2026-07-19 official global pricing kontrolünde `userRatingCount` alanının
  Text Search Enterprise SKU'yu tetiklediği doğrulandı. Aylık ücretsiz kullanım
  sınırı 1.000 event; sonraki ilk dilim liste fiyatı 35 USD / 1.000 event'tir.

## Periyodik fetch — Places API Legacy

- Webapp canlı provider araması yapmaz; yalnızca DB/catalog venue'larını arar.
- Fetch venue seçmez, `config/catalog.yaml` içindeki `place_id` kayıtlarını
  işler. Kataloğa ekleme discovery üzerinden yapılır.
- Başlangıç cadence'i haftalıktır; config değişikliğiyle günlük yapılabilir.
- Review içeren tüm çağrılar Legacy Place Details üzerinden yapılır.
- Her venue için `reviews_sort=newest` ve `reviews_sort=most_relevant` çağrıları
  yapılır.
- Review metninin ve dedup anahtarının çağrılar arasında stabil kalması için
  `reviews_no_translations=true` kullanılır.
- Her response ham payload olarak kendi request variant bilgisiyle saklanır.
- İki sıralamada görülen aynı review, logical snapshot içinde canonical review
  anahtarıyla deduplicate edilir; her iki sıralamadaki görünümü ve rank bilgisi
  ayrıca korunur.
- Periyodik fetch field mask'i minimaldir: `name`, `business_status`, `rating`,
  `user_ratings_total`, `price_level`, `reviews`.
- Timeout, sınırlı retry/backoff, hata sınıflandırma ve fetch-run özeti bulunur.
  Live fetch'te `--no-retries` adapter retry sayısını sıfıra indirir; böylece 30
  venue × 2 review sort için onaylanan azami 60 HTTP isteği teknik olarak
  aşılmaz.
- Yeni snapshot'taki provider name değeri bir önceki tamamlanmış snapshot'tan
  farklıysa `venue_name_changed` koduyla WARNING log üretilir. Önceki ve yeni
  name fetch özetinde gösterilir. Bu kontrol yalnızca operasyoneldir; score ve
  confidence'ı etkilemez ve venue kataloğunu otomatik değiştirmez.
- Legacy endpoint erişilemez olursa otomatik olarak başka endpoint/provider'a
  geçilmez; durum proje sahibine bildirilir ve alternatif birlikte kararlaştırılır.

## Configuration ve secrets

- API key yalnızca environment üzerinden alınır; kodda veya version control'da
  bulunmaz.
- `.env` commit edilmez, `.env.example` sağlanır.
- Eryaman venue kataloğu discovery tarafından `config/catalog.yaml` dosyasına
  yazılır. Task 2'de `--target-count 40` ve config değişikliğiyle genişleme code
  değişikliği gerektirmez.
- Hedef venue sayısı, cadence, yarıçap, filtre eşikleri, brand sınırı, freshness
  cezası ve category kotaları hardcode edilmez; data-collection config'tedir.
- Score weight ve normalization parametreleri versioned config olarak tutulur.

## Faz 2'de netleştirilecek

- Places Aggregate API ile 40 venue ve daha sonra tüm Ankara genişlemesinde
  bölge bölge, 20'şer venue'luk gruplar halinde fetch kurgusu.
- Kullanıcı talebiyle kataloğa venue ekleme akışı gelirse Autocomplete tabanlı
  canlı arama/tamamlama.
- Katalog kurulumunda venue başına 1-2 Place Photo saklanması ve kartta
  `html_attributions` ile gösterilmesi.
- Places New `generativeSummary` ve `reviewSummary` alanlarının Eryaman'da
  bulunabilirlik testi. Uygunsa opsiyonel New Details snapshot çağrısı, Gemini
  ibaresi ve `reviewsUri` atıflarıyla UI gösterimi değerlendirilecek. Bu
  özetler hiçbir durumda score sinyali olmayacak.

## Scoring v4

İlk dört-sinyalli momentum tasarımı `scoring.v1` olarak geçmiş karar kaydında
korunur. Yüksek seviyesini istikrarlı biçimde koruyan mekanları ödüllendirmek
için stability eklenen beş-sinyalli tasarım `scoring.v2` olarak geçmiş karar
kaydında korunur. Structural changes sinyalinin tamamen çıkarıldığı aktif
tasarım `scoring.v3` olarak geçmiş karar kaydında korunur. Stability'nin ürün
açısından daha önemli olduğunun kesinleşmesiyle aktif tasarım `scoring.v4`
olarak versioned edilmiştir.

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
- Yetersiz snapshot sayısı veya zaman kapsaması: `insufficient_data`.

`high_rating_threshold`, `window_days`, `min_snapshots`,
`max_rating_stddev`, `stable_high_value`, `stable_low_value` ve
`volatile_value` dahil tüm eşikler/değerler versioned scoring config'te
tutulur; scorer içinde hardcode edilmez.

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

## Çalışma komutları

Doğrulanmış temel komutlar:

```bash
uv sync
uv run alembic upgrade head
uv run python -m app.discover search --max-requests 1 --reset --no-retries
uv run python -m app.discover status
uv run python -m app.discover freshness --max-requests N --no-retries
uv run python -m app.discover finalize
uv run python -m app.catalog
uv run uvicorn app.main:app --reload
uv run python -m app.fetch --region eryaman
uv run python -m app.scoring.recompute --region eryaman --score-version v4
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

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
