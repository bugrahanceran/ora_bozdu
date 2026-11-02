# Aktif Bağlam

## Şu anki durum — 2026-11-02

- Faz 1'in local-first webapp'i ve Scoring v6 aktif. Puanlama; snapshot
  agregatlarını ve varsa Apify review corpus'unu kullanır.
- Venue discovery, Places API (New) Nearby Search ve bölge bazlı grid ile
  yapılır. 2026-11-02 güncellemesinde Legacy Places Details freshness adımı
  ve cache'teki freshness verileri kaldırıldı. `app.discover` CLI aşamaları
  `search`, `status` ve `finalize`'dır.
- Hard filtreyi geçen yeni adaylar, review tarihi kontrolü olmadan kataloğa
  eklenir. `selection_score` adayları review sayısına göre raporda sıralar;
  seçim limiti değildir. `finalize`, bölgenin `tracked_venue_limit` değerine
  göre tracked mekanları ve Places aramasında görülen güncel review sayılarını
  yeniden hesaplar.
- Armada için discovery pipeline ve katalog 2026-11-02'de yenilendi.
  Armada config'i 400 m grid hücre yarıçapı ve 500 tracked mekan limiti
  kullanır. Eryaman'ın config'i bağımsızdır.
- Periyodik snapshot ve review corpus'u `app.backfill fetch` ile Apify'dan
  alınır. `app.fetch` Legacy Google Place Details akışı olarak kodda durur,
  ancak standart toplama akışında supersede edilmiştir.
- Operasyon planı discovery ve Apify toplamayı ayda bir elle çalıştırmaktır;
  scheduler yoktur. Snapshot config cadence'i `biweekly` ve anchor tarihine
  hizalıdır, aylık period bucket desteği yoktur.

## Güncel çalışma akışları

Yeni bir discovery taraması için bölge config'i ve katalog birlikte seçilir.
Önce `search --max-requests 0 --reset` ile grid/istek sayısı kontrol edilir;
bu, mevcut cache checkpoint'ini yenisiyle değiştirir; yarım koşuya devam ederken
`--reset` kullanılmamalıdır.
onaylanan API koşuları bounded `search` çağrılarıyla tamamlanır; son olarak
`finalize` yerel katalog ve raporu üretir. Her yeni taramada `--reset`
kullanılmalıdır; tamamlanmış cache kendiliğinden yeniden taranmaz.

Apify toplamasında önce `app.backfill fetch --plan` ile tracked mekan sayısı,
period ve maliyet tahmini kontrol edilir; ücretli actor koşusu yalnızca
onaydan sonra yapılır. Armada komutlarında `--region armada` ve ilgili
`--data-collection-config` / `--catalog` dosyaları kullanılmalıdır.

## Kesinleşen ürün ve teknik kararlar

- “Bozdu” / “Coştu” mevcut kalite seviyesinden çok zaman içindeki değişim
  yönünü anlatır.
- Scoring v6 aktif ve versioned'dır. Ağırlıklar: rating trajectory `%30`,
  review velocity/acceleration `%20`, sentiment/keyword drift `%20`,
  seviyeyle koşullu stability `%30`.
- Apify `place_snapshots` agregatlarını ve `venue_reviews` review corpus'unu
  üretir. Corpus varsa v6 count-split trajectory, review-consistency stability
  ve sentiment/keyword sinyallerinde kullanılır; yoksa snapshot review'larına
  veya mevcut fallback davranışına dönülür.
- Discovery hard filtreleri: `OPERATIONAL`, minimum rating/review sayısı,
  bölge yarıçapı ve config'teki `excluded_primary_types`. Uygun bütün yeni
  adaylar kataloğa eklenir; aynı markanın şube sayısı sınırlandırılmaz.
- `tracked` durumu katalogda kalıp periyodik toplama kapsamını belirler.
  Limit bölge config'indedir; tüm katalog venue'ları webapp'te tutulabilir.
- Discovery, Apify toplama ve webapp birbirinden ayrı çalışır. Webapp yalnızca
  DB'deki mekanları arar; canlı Places araması yapmaz.
- Ham provider verileri korunur; score sonuçları versioned ve yeniden
  hesaplanabilir olmalıdır.

## Sıradaki işler / açık kararlar

- Armada için Apify çalıştırılacaksa önce `--plan` çıktısı gözden geçirilmeli;
  canlı actor koşusu için ayrıca açık onay alınmalı.
- Aylık operasyon planı ile `biweekly` snapshot periodu arasındaki fark
  bilinçlidir ama aylık cadence ekleme kararı henüz verilmemiştir.
- Otomatik zamanlama, şehir kapsamını Eryaman ve Armada ötesine genişletme ve
  Apify `sub_ratings` verisinden kategori-drift sinyali ayrı gelecek işlerdir.
- Google Places type listeleri ve provider fiyatlandırması değişebileceğinden
  yeni canlı koşular öncesinde config kapsamı ve maliyet tahmini tekrar
  doğrulanmalıdır.
