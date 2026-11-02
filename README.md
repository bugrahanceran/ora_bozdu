# ora_bozdu

ora_bozdu, mekanların yalnızca bugün iyi veya kötü olup olmadığını değil, zaman
içinde **Bozdu** mu yoksa **Coştu** mu olduğunu gösteren snapshot tabanlı bir
webapp’tir. Faz 1, Eryaman’da 30 restoran/kafe ile local-first çalıştı. Faz 2,
Eryaman ve Armada’da (Söğütözü) kategori bazlı (yalnızca "restoran"/"kafe"
değil, Google Places API’nin tüm "Food and Drink" tip kümesi) neredeyse
eksiksiz bir mekan envanteri hedefler; her bölge ayrı `Region` kayıtları ve
ayrı config dosyalarıyla yönetilir.

## Nasıl çalışır?

Google Places API geçmiş rating veya review time series sağlamaz. Periyodik
snapshot ve review corpus'u Apify Google Maps Reviews Scraper'dan alınır;
ham actor yanıtı `data/apify-<region>.json` dosyasına, normalize edilmiş
kayıtlar SQLite'a yazılır. Config cadence'i `biweekly` ve anchor tarihine
hizalıdır. Operasyon planı aylık manuel çalıştırma olduğundan aynı cadence
periodundaki tekrarlar idempotent biçimde atlanır.
Rating trajectory ve review velocity gibi zaman serileri yeni snapshot'lar
biriktikçe oluşur.

İzlenecek mekanlar elle yazılmaz. `app.discover`, her bölgenin dairesel arama
alanını küçük hücrelere bölüp (grid) Places API (New) Nearby Search ile her
hücreyi tip bazlı (restoran, kafe, pastane, dondurmacı vb. — Google'ın "Food
and Drink" tip kümesinin tamamı) tarar; local filtre (durum + minimum review
sayısı + bölge yarıçapı) uygulanır ve hard filtreyi geçen **herkes** kataloğa
eklenir — bir "en iyi N'i seç" kırpması yoktur. Aynı markanın tüm şubeleri
ayrı ayrı aday olur; şube sayısı sınırlanmaz. Kataloğun tamamı saklanır,
ancak yalnızca `tracked_venue_limit` içindeki mekanlar periyodik snapshot
toplamasına alınır.

Tracked mekanların snapshot'ları ve review corpus'u tek Apify koşusuyla
alınır. Aggregat rating ve review sayısı `place_snapshots`'a, review kayıtları
`venue_reviews`'e yazılır; Scoring v6 bu corpus'u trajectory, sentiment ve
stability sinyallerinde kullanır. Discovery sırasında ayrıca Legacy Places
Details freshness çağrısı yapılmaz.

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
APIFY_TOKEN=your-apify-token
DATABASE_URL=sqlite:///./data/ora_bozdu.db
VENUE_CATALOG_PATH=config/catalog.eryaman.yaml
DATA_COLLECTION_CONFIG_PATH=config/data_collection.eryaman.yaml
SCORING_CONFIG_PATH=config/scoring.v6.toml
```

`APIFY_TOKEN` yalnızca review backfill (`app.backfill fetch`) için gerekir;
diğer akışlar (discovery/fetch/scoring/webapp) onsuz çalışır.

API key kodda tutulmaz ve `.env` git’e girmez. Discovery için Google Places
API (New) Nearby Search erişimi gerekir. Apify snapshot/backfill için
`APIFY_TOKEN` gerekir. Eski Google Places Legacy fetch CLI'si bulunmaya devam
eder; normal periyodik akışta Apify'ın yerini almıştır.

Her bölgenin kendi config/katalog/cache dosyası vardır:

| Bölge | Config | Katalog | Search cache |
| --- | --- | --- | --- |
| Eryaman | [`config/data_collection.eryaman.yaml`](config/data_collection.eryaman.yaml) | [`config/catalog.eryaman.yaml`](config/catalog.eryaman.yaml) | `data/discovery-search-cache.eryaman.json` |
| Armada | [`config/data_collection.armada.yaml`](config/data_collection.armada.yaml) | [`config/catalog.armada.yaml`](config/catalog.armada.yaml) | `data/discovery-search-cache.armada.json` |

`app.discover` ve `app.fetch` CLI'ları `--data-collection-config` ve
`--catalog` bayraklarıyla bu dosyalardan hangisinin kullanılacağını seçer
(varsayılan `.env`'deki değerdir, yani Eryaman). Her config dosyasında bölge
merkezi, arama yarıçapı (`radius_meters`), grid hücre yarıçapı
(`cell_radius_meters`), aranacak Places tipleri (`included_types`) ve minimum
review sayısı (`min_user_ratings_total`) bulunur. Yeni bir bölge eklemek için
her iki dosyayı da kopyalayıp merkez koordinatını değiştirmek ve boş bir
katalog dosyası (`venues: []`) oluşturmak yeterlidir — code değişikliği
gerekmez.

## Discovery (aylık, `--reset` ile tekrarlanır)

Her bölgenin dairesel arama alanı (`radius_meters`), örtüşen küçük dairelere
(`cell_radius_meters`) bölünür — bir "hücre" aslında **hücre × tip-grubu**
kombinasyonudur, çünkü Nearby Search `includedTypes` başına en fazla 50 tip
kabul eder ve Food & Drink kapsamındaki yaklaşık 150 tip içerir (config'teki
`included_types` otomatik olarak ≤50'lik gruplara bölünür). Her `search`
koşusu `--max-requests` ile sınırlandırılır ve başarılı hücre
çağrıları cache dosyasına checkpoint edilir.

**Önemli — her yeni discovery taraması `search --reset` ile başlar.**
`search`'ün cache'i tüm hücreler tarandıktan sonra (`search_completed: true`)
tekrar çağrılırsa **hiçbir yeni istek yapmaz**, yalnızca durumu yazdırır.
`--reset` mevcut arama checkpoint'ini ve o cache'teki adayları silip yeni
tarama başlatır; yarım kalmış bir koşuyu sürdürmek için `--reset` kullanmayın.
`finalize`, yalnızca bu taramadaki Places review sayılarını kullanarak
`tracked_venue_limit` sıralamasını yeniler; bu nedenle yeni dönem taraması
eski cache'i tekrar kullanmamalıdır. Aylık operasyon planında **her yeni
tarama `search --reset` ile başlatılır**. İstek sayısı bölgenin config'indeki
grid hücreleri ve tip gruplarına bağlıdır; önceden `--max-requests 0` ile
hesaplanabilir.

Yeni bir koşu başlatırken sıfır istekli önizleme (API çağrısı yapmaz; `--reset`
eski cache'i yenisiyle değiştirir. Bu yüzden yalnızca yeni tarama başlatmak
istediğinizde kullanın):

```bash
uv run python -m app.discover search --max-requests 0 --reset \
  --data-collection-config config/data_collection.eryaman.yaml \
  --catalog config/catalog.eryaman.yaml
```

Önizlemeden sonra, onaylı ilk tek-istek smoke (aynı cache'i sürdürür):

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

Arama tamamlanınca `finalize` yalnızca cache ve katalog dosyalarını kullanarak
adayları filtreler, kataloğu yazar ve tracked sıralamasını günceller. Bu aşama
provider çağrısı yapmaz:

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
   markanın şube sayısı sınırlanmaz. Zaten başka bir bölge kataloğunda kayıtlı bir
   `place_id` de burada elenir (bkz. aşağıdaki "bölgeler arası koruma").
4. Hard filtreyi geçen **her** yeni adayı kataloğa ekler — bir "en iyi N'i
   seç" kırpması yoktur; rapor sıralaması yalnızca review sayısına dayanır.
5. Kataloğun tamamını (eski + yeni) `user_ratings_total`'a göre yeniden
   sıralar ve en popüler `tracked_venue_limit` kadarını `tracked` işaretler
   (bkz. aşağıdaki "Takip edilen mekan (tracked) seçimi").
6. [`config/catalog.<bölge>.yaml`](config/catalog.eryaman.yaml) ve
   `reports/discovery-latest.<bölge>.json` üretir.

**Takip edilen mekan (tracked) seçimi:** Kataloğa
eklenmek periyodik snapshot toplamaya girmek için yeterli değildir. `finalize`, her
bölgenin **tüm** kataloğunu (bu turda taranan güncel review sayılarıyla,
taranmayanlar için son bilinen review sayısıyla) `user_ratings_total`'a göre
azalan sıralar; config'teki `tracked_venue_limit` kadarını
`tracked: true`, kalanı `tracked: false` olur — silinmez, kataloğda kalır ve
raporda tracked dışında kalır. `app.backfill fetch` yalnızca
`tracked: true` venue'ları işler (hem katalog hem DB `Venue.is_tracked`
kolonu üzerinden çift katmanlı, `active`/`is_active` ile aynı desen). Bu
**sabit bir seçim değildir**: her `finalize` koşusunda yeniden hesaplanır, bu
yüzden review sayısı artan bir mekan sonraki bir döngüde tekrar top-N'e
girebilir — **ama yalnızca o `finalize`'dan önce yeni bir `search --reset`
tarama tamamlandıysa**. `finalize` DB'ye bağlanmaz; `app.backfill fetch`'in
Apify'dan aldığı güncel sayıları bu sıralamaya katmaz. Hiç review verisi olmayan
(ne bu turda taranmış ne daha önce bilinen) mekanlar mevcut `tracked`
durumunda dokunulmadan bırakılır. Yeni
keşfedilen mekanlara özel bir koruma/grace-period yoktur — Google Places API
açılış tarihi vermediğinden güvenilir bir "ne kadar yeni" sinyali yok; düşük
review sayısıyla başlayan bir mekan organik olarak review biriktirdikçe
doğal yoldan yükselir.

**Bölgeler arası koruma:** aynı gerçek mekanın birden fazla bölge kataloğuna
eklenmesini önlemek için, `catalog.<bölge>.yaml` dosyalarının hepsi
(`config/catalog.*.yaml` glob'u ile) taranır ve diğer bölgelerde zaten
kayıtlı `place_id`'ler finalize sırasında hariç tutulur (DB'deki global
`uq_venue_provider_place_id` constraint'i son çare güvenlik ağıdır). Eryaman ve Armada merkezleri ~16,6km ayrık olduğundan
(sırasıyla ~3km yarıçaplı çemberlerle) bu çakışma normal koşulda
beklenmez.

**Yeni bir bölge eklerken:** ilk `search --reset` öncesi elle boş bir katalog
dosyası (`venues: []`) oluşturulmalıdır — `load_catalog` dosya yoksa hata
verir. Eryaman ve Armada için katalog dosyaları zaten mevcuttur.

**`excluded_primary_types` (2026-07-24 eklendi):** Nearby Search'ün
`includedTypes`'ı bir mekanın TÜM tip etiketlerine bakar (yalnızca
`primaryType`'a değil) — bu yüzden kuaför, market, klinik gibi yemekle
ilgisiz mekanlar da ikincil bir food-tipi etiketi yüzünden sonuçlara
sızabiliyor. Bunlar Google'ın atadığı `primaryType`'a göre local olarak
elenir; `config/data_collection.*.yaml`'daki liste, gerçek Eryaman
koşusunda bulunan somut örneklere (kuaför, berber, market, klinik, havuz,
oyun evi, simülasyon merkezi vb.) dayanır. Alakasız mekanlar kataloğa
eklenmez.

## Legacy Google fetch (ikincil / supersede edildi)

> **Not:** Periyodik snapshot artık **Apify** ile alınıyor (bkz. "Veri çekimi —
> Apify"); Apify agregat rating/sayıyı da verdiğinden bu paralı Google Place
> Details akışının yerini aldı. `app.fetch` uyumluluk/manuel kullanım için
> duruyor; standart veri toplama için `app.backfill fetch` kullanılır.
> Discovery ayrı olarak Google Places API (New) Nearby Search kullanır.

Legacy akışın planını provider'a çıkmadan görmek için:

```bash
uv run python -m app.fetch --region eryaman --plan
uv run python -m app.fetch --region armada --plan --data-collection-config config/data_collection.armada.yaml --catalog config/catalog.armada.yaml
```

`app.fetch` çalıştırılacaksa canlı API kullanımı ve retry sınırı önceden
incelenmelidir. Standart periyodik toplama için Apify planı:

```bash
uv run python -m app.backfill fetch --region eryaman --plan
```

`--plan` API çağrısı yapmaz. Gerçek Apify koşusundan önce çıktıyı ve maliyet
tahminini inceleyin; çalıştırma:

```bash
uv run python -m app.backfill fetch --region eryaman
```

Armada için `--data-collection-config config/data_collection.armada.yaml`
ve `--catalog config/catalog.armada.yaml` seçeneklerini ekleyin.

**Zamanlama:** `app.discover` (`search --reset` → bounded `search` → `finalize`)
ve `app.backfill fetch` elle çalıştırılır; scheduler yoktur. Operasyon planı
aylıktır, snapshot config cadence'i ise `biweekly` ve anchor tarihine
hizalıdır. Aylık period bucket henüz desteklenmiyor.
Otomatik zamanlama (ör. bir CI/CD pipeline'ında scheduled job) Faz 4
kapsamında değerlendirilecek — `cron` doğası gereği takvim alanlarıyla
çalışır ve "iki haftada bir" gibi epoch-tabanlı bir periyodu doğrudan ifade
edemez, bu yüzden otomatik hale getirilirse `cadence_anchor_date` ile aynı
parity kontrolü job seviyesinde de ayrıca uygulanmalıdır.

`fetch.cadence` config’te `daily`/`weekly`/`biweekly` arasında
değiştirilebilir; `biweekly` seçiliyken `cadence_anchor_date` zorunludur
(periyot sınırlarının hangi Pazartesi'ye hizalanacağını belirler).

## Veri çekimi — Apify (snapshot + review backfill)

Google Places Place Details her çağrıda bir mekanın yalnızca **~5 review'unu**
verir ve agregat rating popüler mekanlarda atıldır; üstelik bu SKU **paralıdır**.
Apify'ın [Google Maps Reviews Scraper](https://apify.com/compass/google-maps-reviews-scraper)
actor'ü her review item'ında hem mekanın **agregatını** (`totalScore` = rating,
`reviewsCount` = toplam sayı, `title` = ad) hem de **~50 en yeni review'u** (tarih
+ yıldız + metin + kategori alt-puanları) döndürür. Bu yüzden Apify **tek koşuda**
hem `place_snapshots` (skorun stability/velocity/trajectory zaman serisi) hem de
`venue_reviews` corpus'unu (`source=backfill`; daha güçlü `sentiment_keyword_drift`
+ v6 count-split trajesi + review-consistency istikrarı) üretir ve **paralı Google
Place Details fetch'inin yerini alır** (bu nedenle `app.fetch` artık supersede
edilmiştir; yalnızca discover Nearby Search'te Google'da kalır).

**Kapsam / kayıplar:** Apify reviews çıktısında `business_status` ve `price_level`
yoktur. `price_level` skorda zaten kullanılmıyordu (zararsız). `business_status`
kapalı-tespiti için kullanılıyordu; kapanan mekan yeni review almadığından
**dormancy sinyali onu doğal olarak yakalar**, o yüzden Apify snapshot'larında bu
alanlar `NULL` bırakılır. Agregat rating/sayı hâlâ Google'ın gösterdiği değerdir
(Apify onu okur), yani ground-truth kaybı yoktur.

Apify kullanımı ücretlidir ve toplam maliyet tracked mekan sayısı, dönen review
sayısı ve güncel fiyatlandırmaya bağlıdır. Her koşudan önce `--plan` çıktısını
ve Apify'ın güncel fiyatlarını kontrol edin; token `.env` içindeki
`APIFY_TOKEN`'dır. Ücretli actor koşusu yalnızca onaydan sonra yapılır.

Akış:

```bash
# 1. Ön izleme (actor çalıştırılMAZ): kaç mekan, cadence/period, tahmini review, maliyet
uv run python -m app.backfill fetch --region eryaman --plan

# 2. Onay sonrası gerçek çağrı: Apify actor'ünü tracked place_id'lerle çalıştırır,
#    ham yanıtı data/apify-eryaman.json'a yazar, place_snapshots + venue_reviews'e
#    yazar ve v6 skorlarını yeniden hesaplar (tek komut).
uv run python -m app.backfill fetch --region eryaman
```

Apify her review item'ında Google'ın `ChIJ...` `placeId`'sini döndürdüğünden join
**doğrudan `provider_place_id` üzerinden** yapılır (slug köprüsü yok). Hem snapshot
(`venue + cadence + period_start`) hem review (`venue_id + dedup_key`) upsert'i
idempotenttir — aynı yanıt/period iki kez işlenince duplicate oluşmaz. Kaydedilmiş
bir Apify JSON'u yalnızca corpus'a `app.backfill import --input <dosya>` ile de
alınabilir (yeni çağrı olmadan).

## Scoring v6

Score formülü swappable ve versioned’dır. Aktif ağırlıklar
[`config/scoring.v6.toml`](config/scoring.v6.toml) dosyasındadır (v5 frozen
kalır, hâlâ yüklenebilir):

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

**Yorum-tabanlı traje ve istikrar (v6):** Agregat rating popüler mekanlarda
atıldır — 3000+ review'lu bir yerde gerçek bir kalite düşüşü (300 taze 1-yıldız)
ortalamayı neredeyse hiç oynatmaz. v6, bir mekanın **backfill review corpus'u
varsa** (bkz. aşağıdaki "Veri çekimi — Apify") iki sinyali doğrudan yorumlardan
üretir:

- **`rating_trajectory` — count-split:** corpus tarihe göre sıralanıp **newest
  yarı vs older yarı** (takvime göre değil, **sayıya** göre) yıldız ortalaması
  karşılaştırılır. 50 review kaç günü kaplarsa kaplasın çalışır — yoğun mekanın
  newest 50'si haftaları, sakin mekanınki yılları kaplar, ikisi de trend verir.
  Corpus bölünemeyecek kadar inceyse (`< 2 × review_min_per_split`) v5'in agregat
  snapshot deltasına düşer. `details.mode` = `review_split` / `aggregate_snapshot`.
- **`stability` — review-consistency:** corpus 5 zaman-sıralı bucket'a bölünür,
  bucket yıldız-ortalamalarının stddev'i rating **seviyesinin** oynaklığını verir
  (`> review_max_level_stddev` → volatile; `≥ high_rating_threshold` → stable_high;
  yoksa stable_low). Böylece istikrar **snapshot birikmesini beklemeden** çıkar.
  Eşik (0.65), 10'luk bucket'larda integer-rating gürültü tabanının (~0.38)
  üstüne konur ki "volatile" gerçek savrulmayı işaretlesin, gürültüyü değil.
  Corpus yoksa v5'in snapshot-volatilite davranışına düşer. `details.mode` =
  `review_consistency` / (snapshot fallback).

Aynı corpus `sentiment_keyword_drift`'i de besler (5-10 yerine ~50 review).
Corpus `stability`'yi `available` yaptığından erken-faz güven tavanı (0.45) artık
yalnızca ne snapshot ne corpus'u olan mekanlarda uygulanır — dolayısıyla corpus'lu
mekanlarda güven gerçek sinyal gücünü yansıtır.

Geçmiş skorları yeniden hesaplamak için:

```bash
uv run python -m app.scoring.recompute --region eryaman --score-version v6
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
venue’ları arar. Zincir şubeleri Google'da çoğu zaman birebir aynı adı
taşıdığından (`Arabica Coffee House` × 5), arama sonuçları her mekanın en son
snapshot'ındaki rating + review sayısını da gösterir — şubeleri ayırt etmenin
elimizdeki (adres/konum `0003`'te düşürüldüğü için) tek insani yolu budur.
Henüz hiç snapshot'ı olmayan (takip edilmeyen) mekanlar rating yerine "takip
edilmiyor" etiketiyle işaretlenir.

## Test ve kalite

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run alembic check
```

Testler gerçek API’ye çıkmaz. Nearby Search grid üretimi, discovery take-all
mantığı, takip edilen (tracked) mekan seçimi ve yeniden
sıralaması, bölgeler arası koruma, Legacy review sort parse (adapter genel
çoklu-sort'u destekler, aktif config tek `newest` ister), review
deduplication, günlük/haftalık/iki haftalık cadence idempotency,
partial-fetch rollback, operasyonel uyarılar, fetch `--plan`, review backfill
(Apify parse, placeId join, idempotent upsert, `fetch --plan`), Scoring v6
(count-split trajesi + review-consistency istikrarı + corpus-tercihi + fallback) ve web kartı
fixture’larla doğrulanır (backfill testleri Apify actor'ünü çağırmaz).

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
argümanlar (örn. `--data-collection-config config/data_collection.armada.yaml
--catalog config/catalog.armada.yaml`) komut sonuna eklenir. `docker compose
run <servis> <args>` o servisin sabit `command:`'ını **değiştirir**, üzerine
eklemez — `fetch` servisinin varsayılan komutu `alembic upgrade head &&` ile
başladığından, ekstra argümanlarla çalıştırılan bir `run` bu adımı atlar.
Bölgeye özel canlı komutlarda migration adımını ayrıca doğrulayın; gerekirse
önce migration'ı uygulayıp komutu doğrudan `uv run` ile çalıştırın.

Servisler aynı `uv.lock` dosyasını kullanır. `.env`, image içine kopyalanmadan
read-only dosya olarak mount edilir. Fetch/web `./data` SQLite volume’unu,
discovery ise host’taki `./config` ve `./reports` dizinlerini kullanır.

## Veri modeli

Ana tablolar:

- `regions`, `venues`
- `fetch_runs`, `fetch_run_warnings`
- `place_snapshots`, `snapshot_payloads`
- `snapshot_reviews`, `snapshot_review_appearances`
- `venue_reviews` (scraped backfill corpus, `source=backfill`)
- `score_results`

Apify'dan içe alınan tarihsel review'lar `venue_reviews` tablosunda
`source=backfill` olarak tutulur. Google Places Legacy akışının eski
`snapshot_reviews` kayıtlarında `source=places_api` bulunabilir.
