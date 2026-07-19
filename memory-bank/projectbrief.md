# ora_bozdu — Proje Özeti

## Amaç

ora_bozdu, mekanların zaman içinde nasıl değiştiğini veriyle görünür kılan bir
üründür. Temel soru, bir mekanın yalnızca bugün iyi veya kötü olup olmadığı
değil, zaman içinde **Bozdu** mu yoksa **Coştu** mu olduğudur.

Kullanıcı webapp içinde bir mekan arar ve mekanın değişim yönünü gösteren
Bozdu/Coştu kartını görür. Kart, mekanın konumunu solda Bozdu ve sağda Coştu
olan bir bar üzerinde gösterir; kararı etkileyen sinyalleri kısa bir “change
story” ile açıklar.

## İki ana ürün ayağı

1. **Webapp:** Google Maps/Places verisinden zaman içinde mekan değişimini
   ölçen, aranabilir ve veri odaklı ürün.
2. **Şehir bazlı Instagram serisi:** Mekan değişim hikayelerini güçlü görseller
   ve kanıtlarla anlatan içerik ayağı.

Phase 1 yalnızca webapp ayağını kapsar. Instagram içerik üretimi Phase 1
kapsamında değildir.

## Ürün yaklaşımı

- “Bozdu” ve “Coştu” Türkçe product/brand terimleri olarak korunur.
- Değerlendirme mevcut kalite seviyesinden çok değişim yönünü ölçer.
- Kullanıcıya yalnızca bir skor değil, skoru oluşturan sinyaller, veri
  yeterliliği ve koşullu stability durumu da gösterilir.
- Yüksek kalite seviyesini düşük dalgalanmayla korumak, “bozmadı” başarısı
  olarak pozitif değerlendirilir; düşük seviyedeki durağanlık ödüllendirilmez.
- “Her yer zamanla bozuyor” algısı, doğrulanabilir ve açıklanabilir bir veri
  katmanıyla değiştirilir.
- Ham veriler korunduğu için score formülü versioned ve yeniden hesaplanabilir
  olur.

## Phase 1 kapsamı

- Eryaman bölgesinde 30 restoran/kafe ile çalışan local-first MVP.
- Places API (New) Text Search ile deterministik katalog discovery.
- Official Places API Legacy üzerinden başlangıçta haftalık, append-only ham
  snapshot toplama.
- Yalnızca DB içindeki mekanlarda arama.
- Sade venue kartında Bozdu/Coştu change score, genel veri güveni ve skoru
  besleyen sinyallerin kısa açıklamaları.
- FastAPI + Jinja2 webapp, SQLite, SQLAlchemy, Alembic ve bağımsız fetch CLI.
- Sonraki task'ta kod değişikliği olmadan yaklaşık 40 mekana genişleyebilme.

## Phase 1 dışı

- Instagram içerik üretimi ve görsel şablonları.
- Cloud deployment.
- Üçüncü parti veri sağlayıcıları ve geçmiş review backfill uygulaması.
- Kullanıcı hesabı, auth ve favoriler.
- Eryaman dışındaki bölgeler için kullanıcı arayüzü.
- Kullanıcıya açık canlı API venue search.
