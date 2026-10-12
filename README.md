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

Mac uygulaması olarak (Finder'dan çift tıklayabilirsin; gerekirse önce uygulamayı derler):

```bash
open VideoDownloader.command
```

Uygulama sunucuyu kendisi başlatır ve kapanırken durdurur. Günlük:
`~/Library/Logs/VideoDownloader/backend.log`. Bağlantıları `videodownloader://inspect?url=…`
ile, Dock simgesine sürükleyerek ya da pencereye bırakarak da inceletebilirsin. Ayarlar ⌘, ile
açılır.

Tarayıcıda:

```bash
PYTHONPATH=backend uv run python -m app.main   # http://127.0.0.1:8787
```

İlk açılışta **Sistem** sekmesine bak: yt-dlp sürümü, JavaScript motoru ve FFmpeg yetenekleri
orada listelenir. Bir sorun varsa yanında kopyalanabilir çözüm komutu çıkar.

## yt-dlp güncelleme

YouTube sık değişir; format listesi eksildiğinde ilk yapılacak şey budur.

```bash
uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync
```

En kolayı: **Sistem** sekmesindeki "yt-dlp'yi güncelle" düğmesi aynı komutu çalıştırır.

Neden `pip install -U` değil: proje `uv.lock` ile sabitleniyor ve `uv run` her açılışta ortamı
bu dosyaya göre eşitliyor; kilit dosyası güncellenmezse güncelleme bir sonraki açılışta geri
alınır. `yt-dlp -U` ise bu kurulum türünde hiç çalışmaz.

Kararlı sürüm bir sorunu çözmezse gecelik (nightly) sürüme geçmek için `pyproject.toml` içinde
`"yt-dlp[default]>=2026.8.19"` satırını `"yt-dlp[default]>=2026.8.19.dev0"` yap ve:

```bash
uv lock --upgrade-package yt-dlp --prerelease=allow && uv sync
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
