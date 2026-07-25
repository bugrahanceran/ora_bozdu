# Aktif Bağlam

## Şu anda yapılan iş

Phase 1 Task 1'in fixture tabanlı implementation'ı tamamlandı. Otomatik
discovery, YAML catalog ve cadence-aware haftalık fetch hazır. 2026-07-19
tarihindeki ilk onaylı Text Search (New) smoke denemesi `403`, Cloud ayarı
sonrasındaki ikinci deneme hatalı `locationRestriction.circle` nedeniyle `400`
döndürdü. Resmi rectangular restriction + local haversine düzeltmesinden sonra
üçüncü onaylı tek istek başarılı oldu: cafe sorgusu tek sayfada tamamlandı ve
gerçek 2 km filtresinden geçen 16 aday checkpoint'e yazıldı. Üç koşuda da retry
yapılmadı. Ardından ayrıca onaylanan restaurant Text Search ilk sayfası da tek
istek ve sıfır retry ile başarıyla alındı: 16 radius-içi kayıt döndü ve sonraki
sayfa için `nextPageToken` oluştu. İki sorgu arasında tekrar eden kayıtlar
nedeniyle o noktada cache'te toplam 32 ham, 30 unique aday bulunuyordu.
Restaurant ikinci sayfası için ayrıca onaylanan tek istek de başarılı oldu; 18
radius-içi aday daha geldi ve üçüncü sayfa için `nextPageToken` döndü. Güncel
cache toplamı 50 ham, 47 unique adaydır; bunların 31 unique kaydı ilk
`OPERATIONAL + user_ratings_total >= 100` filtresini geçmektedir. Kullanıcıyla
kararlaştırılan `minimum_candidate_pool=30` erken durma kuralı uygulandı;
category minimumları da karşılandığı için search 0 ek HTTP isteğiyle
`minimum_candidate_pool` nedeniyle tamamlandı ve üçüncü sayfa çekilmedi.
Task 1 katalog hedefi kullanıcı kararıyla 20'den 30'a çıkarıldı. 31 uygun aday
arasından preliminary review-count skoru, mevcut category minimumları ve place
ID tie-break ile tam 30 adaylık freshness shortlist oluşturuldu. Kullanıcının
tek koşu için verdiği onayla 30 Legacy `reviews_sort=newest` freshness isteğinin
tamamı retry olmadan başarılı oldu. Tüm venue'larda review tarihi bulundu; en
yeni tarih 2026-07-19, en eski tarih 2026-06-15 ve 30'unun da freshness state'i
`fresh` oldu. Local `finalize` 8 cafe + 22 restaurant olmak üzere 30 venue'luk
kataloğu üretti ve katalog SQLite'a sync edildi. İlk full fetch 30/30 venue için
başarılı tamamlandı: 30 snapshot, 60 ham payload (`30 newest + 30
most_relevant`), 289 deduplicate review ve 300 review-sort appearance SQLite'a
yazıldı. 30 `scoring.v3` sonucu korunurken aynı ham veriden 30 `scoring.v4`
sonucu üretildi; tek snapshot döneminde stability'nin 30/30
`insufficient_data` olması beklenen early-phase davranışıdır.
Ana sayfaya gerçek DB verili 30 satırlık Eryaman skor panosu eklendi. Mekanlar
change score'a göre sıralanır; her satır Bozdu/Coştu mini-axis, rating, review
count, classification ve confidence gösterir. Tümü/Coştu/Dengede/Bozdu
filtreleri light JS ile çalışır ve satırlar mevcut venue detail kartına gider.
Early-phase açıklaması trajectory/stability'nin henüz veri biriktirdiğini açıkça
belirtir.
İlk freshness implementation'ının yalnızca tarih saklayarak ham review
payload'unu kaybettiği tespit edildi. Akış düzeltildi: sonraki freshness
çağrıları ham `newest` payload'u cache'ler; aynı tarihli ilk fetch bunu seed
olarak kullanıp sadece `most_relevant` çağrısı yapar. Adapter iki payload'u tek
snapshot bundle'ında birleştirir. Mevcut 30 live freshness çağrısının ham
response'u geçmişe dönük kurtarılamadığı için mevcut katalogda seed sayısı
sıfırdır.
İlk full fetch sırasında `httpx` INFO logger'ın request URL query parametrelerini
yazdığı ve API key'i log çıktısında görünür kıldığı tespit edildi. Proje sahibine
anahtarı rotate etmesi bildirildi. Fetch logging bundan sonra `httpx` ve
`httpcore` için WARNING seviyesine sabitlendi; request URL'leri INFO çıktısına
girmez. Yeni key doğrulanana kadar başka live API çağrısı yapılmayacaktır.

**2026-07-24 — Faz 2: Discovery genişletmesi (Eryaman + Batıkent).** Kullanıcı
kararıyla discovery mekanizması sıfırdan değiştirildi: Text Search (New) +
tek genel sorgu + freshness-ayarlı "en iyi N'i seç" tamamen kaldırıldı,
yerine Nearby Search (New) + grid tarama + take-all semantiği geldi (bkz.
techContext.md "Discovery — Places API (New) Nearby Search + grid" bölümü,
tam gerekçe ve kaldırılan kod listesiyle). Üç sohbet-içi karar: (1) Eryaman
ve Batıkent iki ayrı, sıkı (~3km yarıçaplı) bölge olarak modellendi — tek
birleşik ~15km alan değil; (2) eski Text-Search kodu tamamen silindi, paralel
bırakılmadı; (3) webapp'te bölge gösterimi (ayrı homepage/kart) bu adımın
kapsamı dışı bırakıldı. Kapsam ayrıca kullanıcı isteğiyle yalnızca
restoran/kafe değil, Google'ın tüm "Food and Drink" Table A kategorisine
(~166 tip) genişletildi. Google'ın "Places Aggregate API"si (eskiden "Places
Insights API") araştırıldı ve reddedildi: `INSIGHT_PLACES` modu yalnızca
sayı ≤100 ise place_id döndürüyor ve döndürdüğü tek şey place_id (isim/rating/
durum yok), bu yüzden Nearby Search'e göre net bir verimlilik kazancı
sağlamıyor. Yeni dosyalar: `app/discovery/geo.py`, `app/discovery/grid.py`,
`app/adapters/places_nearby.py`; kaldırılan dosya: `app/adapters/places_new.py`.
Cache şeması `discovery-search.v2`'ye yükseltildi (hücre-tabanlı, sayfalama
tabanlı değil). 51 test geçti (grid kapsama/determinism, adaptif tek-seviye
bölme, take-all seçim, bölgeler arası koruma dahil), ruff check/format ve
`alembic check` temiz (şema değişmedi). Gerçek config'e karşı sıfır-maliyetli
`search --max-requests 0` dry-run'ı her iki bölge için de 276 arama birimi
(69 coğrafi hücre × 4 tip grubu) üretti — elle yapılan hesapla birebir
doğrulandı. Henüz hiçbir gerçek Nearby Search/freshness API çağrısı
yapılmadı; bir sonraki adım onaylı dry-run/prob/tam koşu aşamalarıdır (bkz.
"Yakın sıradaki işler").

**Aynı gün, devamı — Eryaman'ın ilk gerçek search'ü + adaptif bölmenin
kaldırılması.** Kullanıcı onayıyla Eryaman search'ü gerçek API'ye karşı
çalıştırıldı: 456 istek harcandı (276 temel + 45 hücrenin tavana çarpıp
bölünmesinden gelen +180), 3359 ham aday, dedup+filtre sonrası **410
benzersiz yeni uygun mekan** freshness bekliyor (`search_completed: true`,
gerçek `.env`'deki API key ile). Kullanıcı bu +%65'lik öngörülemez artışı
kabul edilemez buldu ve "en az istekle en çok mekan, verimli altyapı"
önceliğini netleştirdi; sınır taşması gibi küçük hassasiyet kayıplarının
sorun olmadığını belirtti. Karar (`AskUserQuestion` ile onaylandı): **tek
seviyeli adaptif bölme mekanizması tamamen kaldırıldı** — tavana çarpan
hücre artık bölünmüyor, sonucu olduğu gibi kabul edilip yalnızca
`cells_flagged_for_review`'da işaretleniyor. Böylece bir bölgenin toplam
istek sayısı her zaman tam `hücre × tip-grubu` (Eryaman/Batıkent için 276)
— dry-run'da görülen sayı artık kesinleşiyor, sürpriz büyüme olmuyor.
`split_cell` (`grid.py`) silindi; `GridCellState.depth`/`parent_cell_id` ve
`status="split"` yalnızca Eryaman'ın **zaten toplanmış** gerçek verisiyle
geriye dönük uyumluluk için şemada kaldı (yeni hücreler bunları hiç
kullanmayacak). `cells_flagged_for_review` `status=="searched" and
hit_result_cap` olarak yeniden tanımlandı; Eryaman'ın gerçek cache'i
üzerinde yeniden tanım öncesi/sonrası aynı sonucu (19) verdiğini
doğruladım — hiçbir gerçek/ödenmiş veri kaybolmadı. 50 test geçti (2 bölme
testi silindi, 1 yeni davranış testi + 1 geriye-dönük-uyumluluk testi
eklendi), ruff/format temiz. Freshness aşaması (410 istek) henüz
başlatılmadı, kullanıcı onayı bekleniyor.

**Aynı gün, devamı — freshness + finalize + `excluded_primary_types`
filtresi.** Kullanıcı onayıyla 410 mekan için freshness çalıştırıldı
(410/410 başarılı, 0 hata): 405 fresh, 5 stale (en eskisi Göktuğ
Kavurma&Izgara, son review 2025-02-06), 0 mekan hiç review'suz — medyan
son-review-yaşı yalnızca 5 gün. Ardından `finalize` (local, ücretsiz)
çalıştırıldı: 410 eklendi, 30 korundu, katalog 440 oldu. Kategori dağılımını
incelerken yemekle ilgisiz 11 kategori bulundu (isimlerine bakıldı):
`medical_clinic` (diyetisyen kliniği), `barber_shop`, `hair_salon`,
`supermarket` (Bim), `store` (nargile dükkanı), `swimming_pool`,
`amusement_center`, `video_arcade` — bunlar 8'i "açıkça alakasız"; ayrıca 3
sınırda kalan (`sports_complex`="...Pool Cafe", `garden_center`="Ankara
Barbekü", `wedding_venue`=düğün salonu) isimlerinde yemek/ikram ima ediyordu.
Kullanıcı 8'ini kaldırmayı onayladı, 3 sınırdakini tutma önerimi kabul etti.

Kök neden: Nearby Search'ün `includedTypes`'ı (Google'ın FAQ'sinde
belgelendiği gibi) bir mekanın TÜM tip etiketlerine bakar, yalnızca
`primaryType`'a değil — `includedPrimaryTypes` kullanılsaydı bu sızıntı
olmazdı ama gerçek food/drink mekanlarını da (primary type'ı farklı olan)
kaçırma riski vardı. Çözüm: yeni `excluded_primary_types` config alanı +
`apply_hard_filters`'a `rejected_irrelevant_primary_type` reddi eklendi —
bu, **freshness'tan önce** çalışır (`_filtered_candidates` içinde), yani
bundan sonra bu tip mekanlar için hiç Legacy isteği atılmayacak. İki config
dosyasına da (Eryaman + Batıkent) aynı 8 kategorilik dışlama listesi
eklendi.

Zaten kataloğa girmiş 8 mekan `config/catalog.eryaman.yaml`'dan elle
çıkarıldı (440→432). Config/katalog dosyaları değiştiği için discovery
cache'inin kayıtlı `collection_config_hash`/`catalog_hash`'i eski
dosyalarla artık uyuşmuyordu (`_validate_cache` "Discovery config
changed; restart search with --reset" hatası verdi) — **`--reset`
kullanılmadı** (456+410 gerçek/ödenmiş isteği silerdi), bunun yerine
cache'in saklı hash'leri yeni dosyaların gerçek hash'ine göre elle
güncellendi (bu değişikliğin arama sonuçlarını geçersiz kılmadığını,
yalnızca sonraki local filtrelemeyi etkilediğini bilerek). `finalize`
sonra yeniden çalıştırıldı (local, ücretsiz): katalog 432'de sabit kaldı
(8 mekan tekrar eklenmedi), `apply_hard_filters` bu 8 place_id'ye karşı
ayrıca doğrudan test edilip `rejected_irrelevant_primary_type=8` verdiği
kanıtlandı. 51 test geçti, ruff/format temiz, `alembic check` temiz.

Eryaman durumu: **432 mekan** kataloğa girdi (henüz DB'ye sync edilmedi —
o, bir sonraki `app.fetch` koşusunda `sync_catalog` ile olacak, aynı
zamanda bu 402 yeni mekan için "snapshot 1"i üretecek). Sıradaki adım
kullanıcı onayıyla ya `app.fetch --region eryaman` (gerçek snapshot'ları
almak) ya da Batıkent'in aynı akışla (dry-run→search→freshness→finalize)
başlatılması.

**2026-07-25 — Takip edilen mekan (tracked) seçimi + iki haftalık cadence
(implementasyon tamamlandı, gerçek veriye henüz uygulanmadı).** 432
mekanlık Eryaman kataloğunun tamamını 2 haftada bir Legacy Detail ile
izlemek gereksiz maliyetli olacağından, kullanıcı `user_ratings_total`'a
göre en popüler `tracked_venue_limit` (`200`) kadarını aktif izlemeyi,
geri kalanını kataloğda tutup fetch etmemeyi istedi — ve bunun **sabit bir
seçim değil**, her aylık `finalize`'da yeniden hesaplanan dinamik bir
seçim olmasını (review sayısı büyüyen bir mekan tekrar top-N'e girebilsin)
netleştirdi. Aynı oturumda iki ayrı karar birleşti: fetch cadence'i
`weekly`'den `biweekly`'e düşürüldü; Legacy fetch tek sort'a (`newest`)
indirildi çünkü `rating`/`price_level` zaten sort'tan bağımsız `fields`
ile geliyor ve `most_relevant`'ın scoring'e katkısının kontrolsüz/
güvenilmez olduğu kod üzerinden doğrulandı (yalnızca
`sentiment_keyword_drift`'in ufak bir bağımlılığı var, `rating_trajectory`/
`stability`/`review_velocity` zaten `newest` + review sayısıyla tam
besleniyor). Ek bir açık soru olarak "yeni keşfedilen mekanlara koruma/
grace-period gerekir mi?" soruldu ve kullanıcı **hayır, yalnızca review
sayısı** dedi — Google Places API açılış tarihi vermediği için güvenilir
bir "ne kadar yeni" sinyali zaten yok.

Implementasyon: `0004_add_venue_is_tracked` migration'ı (`venues.is_tracked`,
`default=true`); config'e `tracked_venue_limit`, `cadence_anchor_date`
(Eryaman/Batıkent için `2026-07-13`, bir Pazartesi) eklendi,
`review_sorts` validator'ü `{"newest"}`'e daraltıldı; `app/cadence.py`'ye
`anchor_date` parametreli biweekly period hesaplama eklendi;
`app/discovery/selector.py`'ye saf `rank_tracked_venues` fonksiyonu
eklendi ve `build_discovery_result`/`_run_finalize`'a entegre edildi;
`app/fetch.py`/`FetchService.run` artık yalnızca `tracked` venue'ları
işliyor. Kod okurken gerçek bir bug bulundu ve düzeltildi: freshness'ın
seed'lediği `newest` payload'u `fields=reviews`-only olduğundan `name`
içermiyor — eski `reusable` mantığı bunu yine de "kullanılabilir" sayıp
tek-sort modunda state'siz bir payload'la `fetch_place`'i çökertirdi;
düzeltme `reusable`'ı yalnızca `name` içeren payload'larla sınırladı (bkz.
techContext.md "Takip edilen mekan" bölümü, tam detay). 24 yeni test
eklendi (toplam 75 geçiyor), ruff check/format temiz, migration
scratch DB üzerinde upgrade→downgrade→upgrade→`alembic check` ile
doğrulandı.

**Aynı gün, devamı — gerçek DB'ye uygulama.** Kullanıcı onayıyla
`0004_add_venue_is_tracked` gerçek local `data/ora_bozdu.db`'ye uygulandı
(önce yedek alındı, `alembic check` temiz, mevcut 47 DB venue'su
`is_tracked=true` default'uyla doğru geldi). Ardından Eryaman için
`finalize` **mevcut cache ile** (yeni API çağrısı yok) yeniden
çalıştırıldı — ama önce beklenen bir engelle karşılaşıldı: config dosyası
bu oturumda değiştiği için (`tracked_venue_limit`, `cadence`,
`cadence_anchor_date`, `review_sorts`) cache'in saklı
`collection_config_hash`'i artık uyuşmuyordu. Daha önce
`excluded_primary_types` değişikliğinde kullanılan aynı teknikle
(`--reset` kullanmadan, cache'in hash'i CLI'ın kendi `hashlib.sha256`
mantığıyla elle güncellenerek) çözüldü — `catalog_hash` zaten
değişmemişti, yalnızca `collection_config_hash` patch edildi.

**İlk gerçek retarget sonucu:** `catalog_total: 432` (değişmedi, yeni aday
yok), **`tracked_count: 200`, `not_tracked_count: 232`** —
`tracked_venue_limit` ile birebir. En yüksek review'lu tracked mekan
"ANZELHA ERYAMAN" (14164 review); tracked sınırı ~205 review civarında
temiz bir kesim yapıyor (son tracked mekanlar 205-206 review, ilk
not-tracked'ler 192-203 review); 432 mekanın hepsinde review sayısı verisi
var (`user_ratings_total=None` olan yok, hepsi search+freshness'tan geçmiş
olduğu için beklenen). Katalog dosyası (`config/catalog.eryaman.yaml`)
gerçekten yeniden yazıldı; DB'nin `is_tracked` kolonu henüz senkron değil
— bu, bir sonraki gerçek `app.fetch --region eryaman` koşusunda
`sync_catalog` ile olacak (aynı `is_active` deseniyle).

**Aynı gün, devamı — ilk gerçek biweekly fetch.** Kullanıcı önce `--plan`
ile önizlemeyi (200 mekan, 200 istek, `--no-retries` ile kesin üst sınır,
0 seed reuse — seed-safety düzeltmesi ve DB'nin henüz senkron olmaması
nedeniyle beklenen) onayladı, ardından gerçek koşuyu onayladı.
`app.fetch --region eryaman --no-retries` **200/200 başarılı, 0 hata, 0
warning** ile tamamlandı. `sync_catalog` DB'yi 432 mekanlık kataloğa
senkronladı: DB'de `is_active AND is_tracked` tam **200**, `is_active AND
NOT is_tracked` tam **232** — kataloktaki sayılarla birebir (ayrıca
güncel katalogda olmayan 17 eski/pasif venue DB'de kalıntı olarak duruyor,
zararsız, fetch'e hiç girmiyor). 200 yeni `biweekly` snapshot'ı tek
`newest` payload'ıyla yazıldı (toplam `snapshot_payloads=260` — 60'ı Faz
1'in eski haftalık/çift-sort dönemine ait tarihi kayıtlar, 200'ü bugünkü).
Örnek gerçek veri: "ANZELHA ERYAMAN" 4.4★/14164 review, "Köfteci Yusuf"
3.7★/9582 review — finalize'daki review sayılarıyla neredeyse birebir
örtüşüyor. Gerçek API'ye çıkıldı; hiçbir şey henüz commit edilmedi.

**Aynı gün, devamı — venue kartına harita linki.** Kullanıcı UI'ı
tarayıcıda incelerken iki soru sordu: (1) hatayus'un (geçen haftaki bir
Faz 1 venue'su) 2. snapshot'ı gelmiş mi — DB'den doğrulandı: evet, 2
gerçek snapshot var (`weekly`/2026-07-19/1572 review,
`biweekly`/2026-07-25/1574 review); idempotency anahtarı `cadence`'i de
içerdiği için weekly→biweekly geçişi bu turu "hiç çekilmemiş" saydı — tek
seferlik geçiş etkisi, scoring `cadence`'e bakmadan yalnızca
`snapshot_date` sırasına göre okuduğu için trajectory hesabı etkilenmedi.
(2) Venue kartına konum linki eklenebilir mi, konum verisi var mı — ham
koordinat yok (`0003`'te kaldırılmıştı) ama her venue'nun
`provider_place_id`'si var; bundan bir Google Maps place_id-linki
üretilebileceği açıklandı ve onaylandı. Uygulama: `app/main.py`'ye
`_maps_url` helper'ı (place_id yoksa `None`), `venue.html`'e kart(lar)ın
altına koşullu "Haritada gör ↗" linki, `app.css`'e `.map-link` stili.
2 yeni/güncellenen test (`test_web.py`, toplam 76 geçiyor), ruff temiz.
Dev server yeniden başlatılıp gerçek bir venue'da (`anzelha-eryaman`)
canlı doğrulandı — link doğru `query_place_id` ile geliyor.

## Kesinleşen kararlar

- Puanlama yaklaşımı: **A — normalize edilmiş ağırlıklı change score +
  confidence**, aktif version `scoring.v5` (2026-07-24'te `v4`'ten devraldı;
  ağırlıklar değişmedi, stability'ye dormancy cezası eklendi — bkz. aşağıdaki
  2026-07-24 kaydı).
- Ağırlıklar (v4'ten beri sabit): rating trajectory `%30`, review velocity
  `%20`, sentiment/keyword drift `%20` ve stability `%30`.
- Domain `change_score` değeri `-100..+100`, UI bar position `0..100` olur.
- Venue detay kartında barın yanında yalnızca genel `Veri güveni` pill'i
  gösterilir. Classification/stability pill'leri ve bar altındaki tekrar eden
  change-story metni kaldırılmıştır; sinyal açıklamaları ayrı bölümde kalır.
- `stability_state` score çıktısında ve API'de korunur; şimdilik ayrı bir UI
  rozeti olarak gösterilmez.
- Sinyal bazındaki `reliability`, genel güvenle karışmaması için UI'da `Kanıt
  gücü` etiketiyle gösterilir.
- Tek bir mevcut rating gözlemi tek başına değişim veya stability sinyali
  sayılmaz; rating level, delta, trajectory ve volatility ancak yeterli
  snapshot penceresi oluştuğunda değerlendirilir.
- Signal weight ve normalization değerleri versioned config'te tutulur.
- Eksik sinyallerde yalnızca mevcut ağırlıklar yeniden normalize edilir; düşük
  veri miktarı skoru confidence üzerinden nötre yaklaştırır.
- Official API response'ları append-only ham snapshot olarak kalıcı saklanır.
- Ham yazım için configuration/uyum kapısı olmayacaktır.
- Discovery Places API (New) ile otomatik ve deterministik yapılır; kullanıcı
  seçim raporunu denetler. **Güncel mekanizma (Faz 2, 2026-07-24):** Nearby
  Search + grid tarama, iki bölge (Eryaman + Batıkent), hard filtreyi geçen
  **herkesi** alan take-all semantiği — Text Search/tek-sorgu/`minimum_candidate_pool`/
  `target_count` tamamen kaldırıldı; ayrıntı için `techContext.md`'nin
  "Discovery — Places API (New) Nearby Search + grid" bölümüne bakılmalı, bu
  maddeler artık yalnızca o karara giden tarihi bağlamdır.
- Cafe/restoran dağılımı hiçbir zaman ayrı bir seçim hedefi olmadı; Faz 2'de
  kapsam daha da genişledi — yalnızca cafe/restoran değil, Google'ın tüm
  "Food and Drink" tip kümesi (~166 tip) taranıyor.
- Fetch cadence'i `biweekly`dir (Faz 2, 2026-07-25; önce `weekly`),
  `cadence_anchor_date`'e hizalanır; config ile `daily`/`weekly`'ye de
  dönülebilir.
- Idempotency aynı cadence periodu + venue + review sort düzeyindedir.
- Fetch venue seçmez; yalnızca bölgeye özel `config/catalog.<bölge>.yaml`
  içindeki, **hem aktif hem takip edilen** (`tracked: true`) `place_id`
  kayıtlarını işler — takip edilen alt küme her aylık `finalize`'da
  `user_ratings_total`'a göre yeniden hesaplanır (bkz. 2026-07-25 kaydı).
- Bir venue'nun config'te zorunlu tüm review-sort çağrıları tek atomik
  snapshot transaction'ı olarak persist edilir; partial fetch aynı cadence
  periodundaki retry'ı engellemez.
- Place Details Legacy artık tek review sıralamasıyla (`newest`) çağrılır
  (Faz 2, 2026-07-25; önce `most_relevant` + `newest` ikisi de çağrılıyordu
  — adapter genel olarak hâlâ çoklu sort'u destekler).
- Aynı review iki listede bulunursa canonical review tek tutulur; sort ve rank
  bilgileri appearance kayıtlarında ayrı korunur (tek-sort modunda pratikte
  tetiklenmez, mekanizma jenerik kalır).
- Provider-independent adapter sözleşmesi uygulanır; Task 1'de official
  `places_api_new` discovery ve `places_api` Legacy details adapter'ları bulunur.
- Testler gerçek API'ye çıkmaz; gerçekçi fixture payload'ları kullanır.
- Gelecekteki üçüncü parti backfill son 6 ayla sınırlıdır ve Task 1 dışındadır.
- Score formülü versioned olur; geçmiş snapshot'lar için `recompute` komutu
  tasarlanır.
- Stability seviyeyle koşullu dördüncü sinyaldir: yüksek seviye + düşük
  dalgalanma pozitif “bozmadı” katkısı verir; düşük seviye + düşük dalgalanma
  nötr veya hafif negatiftir.
- `stable_high` UI'da pozitif **İstikrarlı** rozeti üretir. `stable_low`,
  `volatile` ve `insufficient_data` ayrı durumlar olarak korunur.
- Structural changes score signal'ı yoktur. `business_status`, name ve
  `price_level` score/confidence hesabına girmez. `price_level`, keyword drift
  teyidi olarak kullanılmaz.
- Provider name bir önceki snapshot'tan farklıysa `venue_name_changed` WARNING
  log ve fetch özetine eklenir. Katalog değişikliği otomatik yapılmaz.
- Kontrollü canlı deneme ve tek mekan retry için fetch CLI opsiyonel
  `--venue <slug>` filtresini destekler.
- Legacy endpoint erişilemezse fallback yapılmadan kullanıcıya bildirilir.
- Hedef sayısı, cadence, radius, filtre eşikleri ve kotalar config-driven olur.
- Gerçek API'ye giden her discovery/fetch koşusu öncesinde açık kullanıcı onayı
  alınır; development testleri yalnızca fixture kullanır.
- Her ücretli koşu onayında çalıştırılacak komut, endpoint/aşama ve azami HTTP
  istek sayısı açıkça gösterilir. Fiyat bilgisi yalnızca ilk referans için
  istenmiştir; kullanıcı tekrar istemedikçe her onayda tekrarlanmaz.
- Onay sunumunda endpoint bazında istek sayısı, toplam istek ve retry durumu
  kısa bir görsel özetle gösterilir. Fiyat yalnızca ilk canlı istek öncesinde
  bir kere doğrulandı; kullanıcı yeniden istemedikçe sonraki onaylarda fiyat
  hesabı tekrarlanmaz.
- Discovery `search`, `freshness` ve local-only `finalize` aşamalarına ayrılır.
  `--max-requests` ve `--no-retries` ile onaylanan ücretli çağrı sınırı teknik
  olarak uygulanır; search/freshness ilerlemesi cache'e checkpoint edilir.
- (Tarihi not, artık geçerli değil) Text Search (New) dairesel
  `locationRestriction` kabul etmediği için rectangular viewport + local
  haversine filtresi gerekiyordu. Faz 2'de Nearby Search'e geçildi (bkz.
  techContext.md); Nearby Search `locationRestriction.circle`'ı native kabul
  ettiği için bu workaround artık yok — ama grid'in kare-hücre + çevrel daire
  yaklaşımı kenar hücrelerde benzer bir taşma yarattığından `rejected_outside_radius`
  filtresi aynı amaçla (gerçek `radius_meters`'ı kesin uygulamak) korunuyor.
- 2026-07-24: Tam codebase review'ı sonrası kullanıcı onayıyla altı düzeltme
  sırayla uygulandı (bkz. progress.md "2026-07-24" bölümü). İlgili kararlar:
  - Ana sayfa skor panosunun "son snapshot" seçimi `MAX(id)`'den
    `snapshot_date` + `id` sıralı pencere fonksiyonuna düzeltildi.
  - Sentiment keyword eşleşmesi kelime sınırına (`\b`) geçirildi; bu **v4
    içinde bugfix** sayıldı (yeni score version açılmadı), çünkü formül/ağırlık
    değişmedi — yalnızca implementasyon hatası düzeltildi. Mevcut 30 venue
    `recompute` ile güncellendi. Bilinen sınırlama: Türkçe yüklem ekleri
    (`tazeydi` gibi) artık kelime sınırıyla yakalanmıyor; sıfır eşleşmede
    rating-fallback bunu yumuşatıyor. Bu ayrı, çözülmemiş bir konu değil,
    bilinçli bir ölçek/kapsam kararı.
  - `place_snapshots`'taki hiç dolmayan 6 kolon (`formatted_address`,
    `latitude`, `longitude`, `types`, `website`, `google_maps_url`) ve bunlara
    bağlı `PlaceState` alanları, Legacy parse kodu ve venue kartındaki Google
    Maps linki **kaldırıldı** (dokümante etmek yerine); minimal field mask
    ilkesiyle uyumlu hale getirildi.
  - Discovery tek birleşik Text Search sorgusuna geçirildi
    (`category: general`, `text_query: "restoran ve kafe"`,
    `included_type: null`); `category_minimums` config alanı ve seçimdeki kota
    mantığı tamamen kaldırıldı. Adayın `category`'si artık Google'ın
    `primaryType`'ından türetiliyor. Bu, henüz gerçek API'ye karşı
    çalıştırılmadı — bir sonraki onaylı `search --reset` koşusunda
    `"restoran ve kafe"` sorgu metninin gerçek sonuç kalitesi gözden
    geçirilmeli.
  - `python -m app.fetch --plan` eklendi: provider'a çıkmadan/API key
    gerektirmeden hangi venue'ların atlanacağını, hangilerinin freshness
    cache'inden seed alacağını ve toplam beklenen HTTP istek sayısını basar.
  - `venue_status_changed` operasyonel WARNING'i, `venue_name_changed` ile aynı
    desende eklendi (score/confidence'ı etkilemez).
  - Doğrulama: 33 fixture test, `ruff check`/`format`, migration
    `0003_drop_unused_snapshot_fields` upgrade→downgrade→upgrade→`alembic
    check`, ve gerçek local DB'ye karşı `/health` + ana sayfa + venue kartı
    smoke testi geçti. Gerçek API'ye hiç çıkılmadı.
- 2026-07-24 (devam): Kullanıcı iki discovery filtresini gerçek ham aday
  havuzuna (47 unique aday) karşı doğrulamamı istedi. `min_user_ratings_total`
  filtresinin gerçekten çalıştığı kanıtlandı (16 aday <100 review nedeniyle
  reddedilmişti). `max_branches_per_brand` kodu doğruydu ama gerçek havuzda
  hiç 3+ şubeli marka çıkmadığı için o kural pratikte hiç tetiklenmemişti —
  bug değildi. Kullanıcı ardından iki ürün kararı verdi:
  - Minimum review eşiği `100`'den `50`'ye düşürüldü.
  - `max_branches_per_brand` kuralı **tamamen kaldırıldı**: aynı markanın tüm
    şubeleri artık ayrı ayrı katalog adayı olabilir (5 Starbucks varsa 5'i de
    eklenir). `apply_hard_filters`'ın `existing`/brand-cap parametresi ve
    `FilterResult.rejected_brand_cap` alanı koddan silindi; `brand_key` sadece
    bilgi amaçlı hesaplanmaya devam ediyor. Bu, mevcut 30 venue'luk kataloğu
    etkilemiyor (zaten hiçbirinde brand cap tetiklenmemişti) — yalnızca
    sonraki discovery koşularını etkiler.
  - Doğrulama: güncellenmiş `apply_hard_filters` gerçek 47 adaylık ham havuzda
    tekrar çalıştırıldı (35 kabul, 12 review-count reddi — eşik değişimiyle
    tutarlı), 33 test + ruff check/format geçti.
- 2026-07-24 (push öncesi review): Kullanıcı günün değişikliklerini push
  öncesi 4 soruyla sorguladı; üçü gerçek bulgu çıkardı:
  - **Scoring version semantiği:** Keyword bugfix'i v4 içinde kaldı (yeni
    version açılmadı). Veri bütünlüğü açısından sorun yok (recompute her
    zaman güncel engine koduyla tüm v4 satırlarını tazeler, karışık/eski
    sonuç kalmaz). Ama gerçek bir gedik var: DB'de "bu v4 satırı hangi engine
    koduyla hesaplandı" bilgisi yok — tek kaynak bu memory-bank kaydı ve git
    geçmişi. Kabul edilebilir ama mükemmel değil; ileride scoring engine'in
    kendisini etkileyen (yalnızca weight/threshold değil) benzer düzeltmeler
    birikirse tekrar gözden geçirilebilir.
  - **Freshness gerçekten seçimi etkilemiyor muydu — DOĞRULANMIŞ BUG:**
    `freshness_shortlist()`, gerçek freshness bilinmeden (`newest_review_at=
    None`) hesaplanan preliminary skorla adayları `target_count`'a
    daraltıyordu; freshness sonucu yalnızca finalize'daki ikinci
    `select_candidates` çağrısına giriyordu ama o noktada havuzda zaten tam
    `target_count` kadar aday olduğu için hiçbir aday freshness yüzünden
    elenemiyordu. Düzeltildi: `freshness_shortlist` artık hard filtreyi geçen
    **tüm** eligible adayları döndürüyor, daraltma yalnızca finalize'da gerçek
    freshness bilindikten sonra oluyor. Bu, mevcut tamamlanmış 30 venue'luk
    kataloğu etkilemez (retroaktif değil), yalnızca sonraki discovery
    koşularını düzeltir. Yeni regression testi
    (`test_freshness_can_demote_a_stale_high_review_count_candidate`)
    popüler-ama-durgun bir adayın gerçekten daha taze bir yedekle
    değiştirildiğini kanıtlıyor.
  - **`fetch --plan` retry ile gerçek üst sınırı göstermiyordu — DOĞRULANMIŞ
    EKSİK:** `estimated_http_requests` yalnızca mantıksal (retry'sız) istek
    sayısını gösteriyordu; retry açıkken (varsayılan, `settings.
    http_max_retries=2`) gerçek istek sayısı 3 katına kadar çıkabilirdi ama
    plan çıktısı bunu hiç yansıtmıyordu. `max_retries` parametresi ve
    `worst_case_http_requests_with_retries` alanı eklendi. Gerçek DB'ye karşı
    doğrulandı: retry açıkken 60 mantıksal → 180 worst-case; `--no-retries`
    ile 60/60.
  - **README:** Discovery/fetch bölümleri (ayrı cafe/restaurant sorgusu,
    brand cap, category kotaları, min review=100) tamamen güncellenmedi
    olarak bulundu; birleşik sorgu, kota kaldırma, `min_user_ratings_total=50`,
    brand cap kaldırma, `--plan`, `venue_status_changed` ve freshness'ın artık
    seçimi etkilediği bilgisiyle güncellendi.
  - Doğrulama: 35 test (2 yeni: freshness demote testi + plan retry
    assertion'ları güncellendi), ruff check/format, `alembic check`, gerçek
    local DB'ye karşı `--plan` (retry açık/kapalı) + `/health` + ana sayfa
    smoke testi geçti.
- 2026-07-24 (Scoring v5 — dormancy): Kullanıcı, discovery freshness
  tartışmasından yola çıkarak ürün scoring'i için bir netleştirme yaptı:
  "sadece review'a bakarak durgunluk cezası verilemez; rating sayısı (yıldız/
  oylama) hâlâ artıyorsa mekan fresh sayılır; ikisi de durmuşsa ceza
  uygulanabilir ama mekan asla kataloğdan çıkarılmaz, yalnızca skor Bozdu
  yönüne yaklaşır." Kullanıcı bunu mevcut `stability` sinyaline entegre etmeyi
  seçti (5. sinyal veya review_velocity'ye entegre yerine), süreye göre
  kademeli bir ceza olarak ("4 ay az, 6 ay biraz daha, uzadıkça artar").
  - Bu, formülün davranışını değiştiren bir tasarım kararı olduğu için
    (bugfix değil) yeni bir score version — **`scoring.v5`** — açıldı; v4
    dokunulmadan/frozen kaldı.
  - `ScoringEngine._days_since_activity`: son aktivite tarihi,
    `user_ratings_total`'ın snapshot'lar arası en son arttığı tarih **veya**
    en son review'un `published_at`'i (hangisi daha yeniyse) olarak
    hesaplanır. `ScoringEngine._dormancy_penalty`: `dormancy_grace_days`
    (60 gün) altında ceza yok; `dormancy_full_penalty_days`e (365 gün) doğru
    doğrusal artıp `dormancy_penalty_value`e (-1.0) ulaşır.
  - `-1.0` seçildi (ilk taslak -0.60 idi) çünkü test etti: `stable_high`
    (+0.75) + `-0.60` hâlâ pozitif (+0.15) çıkıyordu — kullanıcının "Bozdu'ya
    yaklaşsın" isteğini karşılamıyordu. `-1.0` ile tam durgunlukta değer her
    zaman net negatife düşüyor.
  - `app/config.py`'nin varsayılan `scoring_config_path`'i VE gerçek `.env`
    dosyasındaki `SCORING_CONFIG_PATH` `config/scoring.v5.toml`'a
    güncellendi (yalnızca default'u değiştirmek yetmiyordu, `.env`'de
    açık `v4` override'ı vardı). Local recompute ile 30 venue v5'e taşındı;
    tek snapshot oldukları için `stability` hâlâ `insufficient_data`,
    dormancy alanları henüz gözlenemiyor (7+ snapshot gerekiyor).
  - Eski `scoring.v4.toml` yeni alanları içermediği için `StabilityConfig`'e
    nötr default'lar eklendi (`dormancy_penalty_value=0.0` vb.) — v4 hâlâ
    yüklenebilir ve davranışı değişmedi.
  - `main.py`'deki `STABILITY_LABELS`'e `dormant: "Sessizleşti"` eklendi
    (`stable_low` zaten "Durgun" etiketini kullandığı için farklı bir isim
    seçildi, karışıklık olmasın diye).
  - Doğrulama: 37 test (3 yeni: kademeli ceza, tam dormancy override, rating-
    count-ile-fresh-kalma), ruff check/format, `alembic check`, gerçek local
    DB'de recompute + `/health`/ana sayfa/venue kartı smoke testi (API
    çıktısında `score.version == "v5"` doğrulandı).
  - Kullanıcı ardından formülün genel tutarlılığını sorguladı: "aktif+istikrarlı
    Coştu'ya güçlü yaklaşıyor mu, durgunluk Bozdu'ya zayıf/kademeli mi
    çekiyor, tüm sinyaller uyumlu mu?" Gerçek `ScoringEngine` ile simüle edilip
    doğrulandı (39 teste 2 yeni regression testi eklendi):
    - Aktif + 4.2 sabit rating → `change_score=26.1`, **costu**, confidence
      %97.3 (güçlü, beklenen).
    - Aynı venue tam durgunlaşınca (0→119→182→371 gün) `change_score`
      26.1→9.7→4.5→-13.5 olarak **kademeli** düşüyor ama yüksek ratingli bir
      venue'da durgunluk TEK BAŞINA asla `bozdu`ya geçmiyor, `dengede`de
      kalıyor (`rating_trajectory` hâlâ nötr olduğu için, sayı hiç
      düşmediğinden) — kullanıcının "zayıf, güçlü düşüş yok" tarifiyle birebir
      örtüşüyor.
    - Aynı durgunluk düşük bir rating'le (3.5, `stable_low` taban) birleşince
      `change_score=-39.6`, **bozdu** — yani durgunluk diğer sinyallerle
      doğru şekilde toplanabiliyor, izole/tavanlı değil.
    - `review_velocity`, durgunluğa geçiş anında geçici bir negatif tepki
      veriyor (ivme/deceleration, `-0.39`'dan `-0.19`'a sönümleniyor) —
      stability'nin kalıcı dormancy cezasıyla çelişmiyor, aynı yöne
      tamamlayıcı katkı yapıyor. `sentiment_keyword_drift` review birikmeyince
      doğru şekilde unavailable oluyor. Confidence tüm senaryolarda sabit
      (%97.3) kaldı çünkü "veriye güven" ile "yön" birbirinden ayrık — dormancy
      yönü etkiliyor, güveni değil (yeterli snapshot geçmişi zaten var).

## Aktif puanlama v5 ağırlıkları

Config üzerinden kesinleşen ağırlıklar:

- Rating trajectory: `0.30`
- Review-count velocity/acceleration: `0.20`
- Review sentiment ve keyword drift: `0.20`
- Seviyeyle koşullu stability (+ 2026-07-24'ten itibaren dormancy cezası):
  `0.30`

Snapshot geçmişi oluşmadan unavailable sinyaller score'a katılmaz. Task 1'de
review tarihlerinden stability proxy zorlanmaz; stability yeterli snapshot
gelene kadar `insufficient_data` olur. Yalnızca sınırlı review ve review-date
proxy'leri bulunan early phase sonucunda confidence için üst sınır uygulanır.
Rating eşiği, dalgalanma penceresi, minimum snapshot sayısı ve stability
katkıları scorer içinde hardcode edilmez; versioned config'e yazılır.

Venice Italian Pizza örneğinde tek snapshot nedeniyle rating trajectory ve
stability unavailable kalırken, 6 recent ve yalnızca 2 older review'dan
hesaplanan sentiment drift `-1.00` ve kanıt gücü `%80` üretmiştir. Legacy
API'nin sınırlı/seçilim yanlı review örneğinde toplam review sayısını doğrudan
reliability kabul etmek fazla iddialıdır. Sonraki scoring kararı için açık öneri:
recent/older cohort başına config-driven minimum review sayısı ve cohort
dengesini dikkate alan reliability; yeterli karşılaştırma yoksa düşük güçlü
recent-level proxy'ye dönüş. Bu değişiklik v4'e sessizce eklenmeyecek, yeni bir
score version olarak kararlaştırılacaktır.

## Son doğrulama sonuçları

- 2026-07-25 (takip edilen mekan + biweekly cadence): `pytest`: 75 test
  geçti (24 yeni: `rank_tracked_venues`, biweekly `period_start_for`,
  seed-safety bugfix, `is_tracked` katalog/DB round-trip, `FetchConfig`
  validator'leri, `finalize` tracked-count entegrasyonu). `ruff check .` ve
  `ruff format --check .`: geçti. `0004_add_venue_is_tracked`:
  upgrade→downgrade→upgrade→`alembic check` önce scratch DB'de, sonra
  kullanıcı onayıyla **gerçek `data/ora_bozdu.db`'de** (yedek alınarak)
  doğrulandı, ikisi de temiz. Eryaman `finalize`'ı gerçek cache ile
  (0 yeni istek) yeniden çalıştırıldı: **200 tracked / 232 not-tracked**,
  katalog 432'de sabit. Gerçek API'ye çıkılmadı (yalnızca local/ücretsiz
  işlemler).
- 2026-07-24: `pytest`: 33 test geçti (6 yeni test: keyword word-boundary,
  genel discovery sorgusu, fetch `--plan`, `venue_status_changed` × 2 senaryo).
  `ruff check .` ve `ruff format --check .`: geçti. Alembic
  `0003_drop_unused_snapshot_fields` dahil upgrade → downgrade → upgrade ve
  `alembic check`: geçti (gerçek local DB üzerinde, yedek alınarak). Gerçek DB
  ile `/health`, ana sayfa (`Eryaman skor panosu` render) ve
  `/venues/mrada-cafe` smoke testi: HTTP 200. Gerçek API'ye çıkılmadı.
- `pytest`: 27 test geçti.
- `ruff check .`: geçti.
- `ruff format --check .`: geçti.
- Alembic `0002_cadence_periods` dahil upgrade → downgrade → upgrade ve
  `alembic check`: geçti.
- Pre-commit configuration validation: geçti.
- Local FastAPI `/health`, DB-only search ve ana sayfa smoke: geçti.
- Güncel dependency setiyle Docker image build, discovery CLI import ve
  container içinde Alembic `0002` + boş katalog sync smoke: geçti.
- Local SQLite `0002` migration'a yükseltildi; doğrulanmamış eski 20 taslak venue
  silinmeden inactive yapıldı. Finalize sonrasında yeni katalog sync edildi ve
  active venue sayısı `30` oldu.

## Yakın sıradaki işler

1. (Faz 2, 2026-07-24'te tamamlandı — artık geçerli değil: eski madde
   "restoran ve kafe" sorgu metninin kalitesini gözden geçirmekti; Nearby
   Search'e geçişle birlikte serbest metin sorgusu tamamen kalktı, konu
   kapandı.)
2. (Eryaman için tamamlandı — 2026-07-24: search 456 istek, freshness 410
   istek, finalize; `excluded_primary_types` filtresiyle 8 alakasız mekan
   temizlendi. Katalog **432 mekan**.) (2026-07-25: takip edilen mekan
   seçimi + biweekly cadence implementasyonu, gerçek DB/retarget
   uygulaması (200 tracked / 232 not-tracked) **ve** ilk gerçek biweekly
   fetch (200/200 başarılı) tamamlandı. Bkz. yukarıdaki 2026-07-25
   kayıtları.) Sırada, kullanıcı onayıyla: Batıkent'in kendi discovery
   akışı (dry-run → search → freshness → finalize, kendi retarget'ıyla) —
   Eryaman tarafında şu an başka bekleyen bir adım yok.
3. Nearby Search'ün gerçek SKU/fiyat kademesini (Text Search'te
   `userRatingCount`'un Enterprise'ı tetiklediği zaten doğrulanmıştı) Google
   Cloud Console'dan doğrulamak — henüz yapılmadı, 456+410 gerçek istek
   sonrası artık daha somut bir maliyet verisiyle kontrol edilebilir.
4. Gerçek snapshotlarla UI/card davranışını ve early-phase confidence
   sunumunu denetlemek.
5. Faz 4: discover (aylık)/fetch (2 haftada bir) tetiklemesini scheduled bir
   pipeline'a (örn. Jenkins) bağlamak — yalnızca not düşüldü, tasarım
   yapılmadı (bkz. techContext.md "Faz 4'te netleştirilecek").

## Açık konular

- Önceki 20 venue listesi doğrulanmamış taslaktır ve nihai katalog sayılmaz.
  Taslak DB kayıtları silinmeden inactive yapıldı. Nihai liste `app.discover`
  tarafından üretilecektir.
- `GOOGLE_MAPS_API_KEY` 2026-07-19 tarihinde kullanıcı tarafından rotate edilip
  `.env` içinde güncellendi. Compose `.env` dosyasını içeriğini render etmeden
  read-only mount eder. Her ücretli sorgu grubu öncesinde ayrıca açık kullanıcı
  onayı alınacaktır.
- Fetch logunda görünür olan önceki key kullanıcı tarafından tekrar rotate
  edildi ve yeni key `.env` altına eklendi. Secret içeriği okunmadı veya
  doğrulama amacıyla ekrana basılmadı; live API blokajı kaldırıldı. Sonraki her
  live koşu için komut ve azami istek sayısıyla ayrıca onay alınmaya devam eder.
- Official pricing'e göre discovery field mask'indeki `userRatingCount`, Text
  Search Enterprise SKU'yu tetikler: aylık ilk 1.000 event ücretsiz, sonraki
  ilk dilim 35 USD / 1.000 event; tek event liste maliyeti yaklaşık 0,035 USD'dir.
- İlk live smoke: onaylanan `search --max-requests 1 --reset --no-retries`
  komutu bir HTTP isteği yaptı ve `403 Forbidden` aldı. Cache'te page/candidate
  oluşmadı. Cloud ayarı düzeltildikten sonra aynı kapsamda yeniden onaylanan
  ikinci koşu da tam bir istek yaptı ve retry yapmadı. Bu kez API
  `locationRestriction.circle` alanını reddederek `400 INVALID_ARGUMENT`
  döndürdü. Adapter rectangular viewport + local haversine radius filtresine
  geçirildi. Aynı komut için ayrıca onaylanan üçüncü koşu bir istek ve sıfır
  retry ile başarılı oldu. Cafe sorgusunda `nextPageToken` dönmedi; 16 radius-içi
  adayın 9'u ilk `OPERATIONAL + user_ratings_total >= 100` filtresini geçiyor.
- Ayrı onayla çalıştırılan restaurant ilk sayfa çağrısı da `1` HTTP isteği ve
  sıfır retry ile başarılı oldu. 16 radius-içi kayıt geldi; `nextPageToken`
  bulunduğu için restaurant search henüz tamamlanmadı. Cafe ile iki tekrar
  dahil 32 ham kayıt, dedupe sonrası 30 unique aday cache'te duruyor.
- Restaurant ikinci sayfası ayrıca onaylanan `1` HTTP isteği ve sıfır retry ile
  başarıyla alındı. 18 radius-içi aday geldi; üçüncü sayfa `nextPageToken`ı
  bulunduğu için search henüz tamamlanmadı. Güncel checkpoint 50 ham / 47
  unique aday içeriyor; 31 unique aday temel operational ve rating-count
  eşiğini geçiyor.
- `minimum_candidate_pool=30` kuralı fixture testiyle eklendi. Mevcut cache
  `search --max-requests 0` ile, API çağrısı olmadan tamamlandı; 31 uygun aday
  bulundu ve restaurant üçüncü page token'ı tüketilmedi. Hedefin 30'a
  çıkarılmasıyla deterministik freshness shortlist tam 30 aday oldu.
- Official 2026-07-15 global fiyat tablosunda Legacy `reviews` alanını tetikleyen
  Atmosphere Data SKU'sunun aylık free usage cap'i 1.000 başarılı istek,
  Legacy Places Details base SKU'sunun cap'i 5.000 başarılı istektir. Bu akışta
  sınırlayıcı free cap 1.000'dir; Cloud projesindeki gerçek kalan kullanım
  Console görülmeden bilinemez.
- Onaylanan toplu freshness koşusu `requests_this_run=30`,
  `freshness_completed=30`, `freshness_remaining=0` ile tamamlandı. Local
  finalize raporu 30/30 selected, 8 cafe ve 22 restaurant gösteriyor.
- Freshness raw-payload reuse düzeltmesi 26 fixture testiyle doğrulandı. Cached
  `newest` bulunduğunda full fetch adapter'ının yalnızca `most_relevant` HTTP
  çağrısı yaptığı regression testi bulunuyor.
- Onaylanan ilk full fetch `requested=30`, `succeeded=30`, `failed=0`,
  `warnings=[]` ile tamamlandı. DB doğrulaması 30 snapshot, 60 raw payload, 289
  canonical review, 300 appearance ve 30 score result gösterdi. Gerçek MRADA
  DB-only search/card smoke'u HTTP 200 ve dolu score ile geçti.
- HTTP client log suppression testi eklendikten sonra toplam 27 test, ruff
  check ve format check geçti.
- Gerçek DB ile ana sayfa 30 scoreboard row ve 4 filter render ederek HTTP 200
  verdi. Webapp `127.0.0.1:8000` üzerinde local olarak başlatıldı; Google API
  çağrısı yapılmadı.
- Sentiment v3 deterministic Türkçe/İngilizce lexicon ve review rating fallback
  ile uygulandı; external model/library kullanılmıyor.
