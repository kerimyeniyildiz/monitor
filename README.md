# TwitterAPI.io Tweet & Haber Monitörü

`monitor.py`, `twitterapi.io` `tweet/advanced_search` endpointiyle **Kırklareli** sorgusunu her 5 dakikada kontrol eder, son 10 tweeti değerlendirir ve Telegram'a yollar. Ayrıca uzaktaki bir liste (veya opsiyonel yerel dosya) içindeki sitemap.xml adreslerini 10 dakikada bir tarar, yeni haber linklerini Telegram'a gönderir; gönderilmiş URL'leri diskte tutarak tekrar yollamaz.

## Kurulum
1. Python 3.9+ kurulu olduğundan emin olun.
2. Bağımlılıkları yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
3. `.env` dosyası oluşturun ve API/Telegram bilgilerinizi ekleyin:
   ```
   API_KEY=new1_f59742315c034163aa71b048cd08e40a
   # Opsiyonel ayarlar:
   # QUERY=Kırklareli
   # QUERY_TYPE=Latest          # veya Top
   # TWEET_LIMIT=10
   # POLL_INTERVAL_SECONDS=300  # tweet kontrol süresi (varsayılan 5 dk)
   TELEGRAM_TOKEN=7971242435:AAEc3N_bkXmASXCjWMnaD-_7P4yO_weH86I
   TELEGRAM_CHAT_ID=7561796744
   # SENT_URLS_FILE=sent_urls.txt      # gönderilen tweet URL’leri
   # NEWS_SENT_FILE=sent_news.txt      # gönderilen haber URL’leri
   # NEWS_LIMIT=10                     # her sitemap taramasında en fazla bu kadar yeni link
   # SITEMAP_LIST_URL=https://example.com/path/to/sitemap_list.txt   # tercih edilen yöntem
   # SITEMAP_LIST_FILE=sitemap.txt     # (opsiyonel) yerel dosya, repo dışı tutun
   # SITEMAP_CHECK_SECONDS=600         # sitemap tarama sıklığı (varsayılan 10 dk)
   # SITEMAP_REFRESH_SECONDS=86400     # sitemap listesini yeniden okuma (varsayılan günlük)
   # HTTP_TIMEOUT_SECONDS=30
   # HTTP_MAX_RETRIES=3
   # HTTP_RETRY_BACKOFF=2
   ```
4. Sitemap listesi için tercih edilen yöntem: Dışarıda barındırdığınız düz metin dosyasının URL’sini `SITEMAP_LIST_URL` olarak verin (her satırda bir sitemap.xml). Eğer URL kullanmazsanız `SITEMAP_LIST_FILE` ile yerel dosya yolu belirtebilirsiniz, fakat bunu repoya koymayın.

## Çalıştırma
```bash
python monitor.py
```
Başlangıçta mevcut tweetleri ve sitemap linklerini tarar, sonra belirtilen aralıklarla devam eder. Gönderilen URL’ler dosyalarda tutulduğu için tekrar gönderilmez.

## Notlar
- API anahtarı `x-api-key` başlığında gönderilir (bkz. [Authentication](https://docs.twitterapi.io/authentication)).
- Tweet sorgusunu `QUERY` ile özelleştirebilirsiniz (örn. `Kırklareli lang:tr`, `Kırklareli from:someuser`).
- Sitemap listesi günlük yenilenir; daha sık yenilemek için `SITEMAP_REFRESH_SECONDS` değerini düşürebilirsiniz. `SITEMAP_LIST_URL` tanımlıysa uzaktaki dosyadan okunur; yoksa `SITEMAP_LIST_FILE` kullanılır (repo dışında tutun).
- Çıktı formatını ve gönderilen alanları `monitor.py` içinde kolayca güncelleyebilirsiniz.
