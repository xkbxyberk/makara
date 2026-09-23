# VideoDownloader

yt-dlp ve FFmpeg üzerine kurulu, yalnızca bu Mac'te çalışan kişisel medya iş istasyonu.
Sunucu sadece `127.0.0.1` üzerinden dinler; hiçbir veri dışarı gönderilmez.

## Kurulum

Gereken hazır araçlar: [uv](https://docs.astral.sh/uv/), Node 22+, ve `ffmpeg` (`brew install ffmpeg`).
YouTube için bir JavaScript motoru gerekir; `deno` önerilir (`brew install deno`).

```bash
cd ~/VideoDownloader
uv sync                      # Python bağımlılıkları (yt-dlp dahil)
cd frontend && npm install && npm run build && cd ..
```

## Çalıştırma

Masaüstü penceresi olarak (Finder'dan çift tıklayabilirsin):

```bash
open VideoDownloader.command
```

Tarayıcıda:

```bash
PYTHONPATH=backend uv run python -m app.main   # http://127.0.0.1:8787
```

İlk açılışta **Sistem** sekmesine bak: yt-dlp sürümü, JavaScript motoru ve FFmpeg yetenekleri
orada listelenir. Bir sorun varsa yanında kopyalanabilir çözüm komutu çıkar.

## yt-dlp güncelleme

YouTube sık değişir; format listesi eksildiğinde ilk yapılacak şey budur.

```bash
uv pip install -U "yt-dlp[default]"
```

`yt-dlp -U` bu kurulumda **çalışmaz** (pip/uv ile kurulduğu için). Kararlı sürüm sorun
çıkarırsa gecelik sürüme geçebilirsin:

```bash
uv pip install -U --prerelease=allow "yt-dlp[default]"
```

## Geliştirme

```bash
./scripts/check.sh    # lint + tipler + pytest + vitest + derleme + uçtan uca testler
```

Testler **hiçbir zaman ağa çıkmaz**; `tests/fixtures/infojson/` altındaki gerçek kayıtları
kullanır. Ağa çıkan tek test isteğe bağlıdır: `RUN_LIVE_TESTS=1 uv run pytest -m live`.

## Bu makinedeki sınırlar

- Bu FFmpeg derlemesinde **libass yok**: altyazıyı görüntünün içine yakmak mümkün değil.
  Altyazıyı dosyaya gömmek (soft subtitle) çalışıyor ve çoğu durumda zaten daha iyi.
- **libwebp yok**: animasyonlu WebP üretilemez, GIF üretilebilir.
- DRM korumalı içerik indirilemez; uygulama DRM korumasını aşmaz.
