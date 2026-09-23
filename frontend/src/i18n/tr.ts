/**
 * Every user-facing string in the app lives here, and nowhere else.
 * The backend only ever returns codes; this file turns them into Turkish.
 * Adding English later means adding one sibling file and a language switch.
 */
export const tr = {
  app: {
    name: 'VideoDownloader',
    brand: 'Medya',
    themeToggle: 'Temayı değiştir',
    themeLight: 'Açık tema',
    themeDark: 'Koyu tema',
    copy: 'Kopyala',
    copied: 'Kopyalandı',
    retry: 'Tekrar dene',
    showDetails: 'Ayrıntıları göster',
    hideDetails: 'Ayrıntıları gizle',
    showMore: 'Devamını göster',
    showLess: 'Daha az göster',
    unknown: 'bilinmiyor',
    soon: 'yakında',
  },
  nav: {
    inspect: 'İncele',
    download: 'İndir',
    library: 'Kütüphane',
    studio: 'Stüdyo',
    doctor: 'Sistem',
    settings: 'Ayarlar',
  },
  inspect: {
    title: 'İncele',
    urlLabel: 'Bağlantı',
    urlPlaceholder: 'Bir video, playlist veya kanal bağlantısı yapıştır',
    submit: 'İncele',
    pasteHint: 'İpucu: herhangi bir yerde ⌘V ile panodaki bağlantıyı doğrudan inceleyebilirsin.',
    dropHint: 'Bağlantıyı buraya bırak',
    emptyTitle: 'Henüz bir şey incelemedin',
    emptyBody:
      'Bir bağlantı yapıştır; bu videonun sunduğu her kaliteyi, her ses dilini ve her altyazıyı burada göreceksin. Hiçbir şey indirilmez.',
    loadingTitle: 'Çözümleniyor',
    loadingBody: 'yt-dlp siteye bağlanıp mevcut bütün parçaları listeliyor. Bu birkaç saniye sürebilir.',
    metadata: 'Bilgiler',
    videoFormats: 'Video kaliteleri',
    muxedFormats: 'Ses ve görüntü birlikte',
    audioTracks: 'Ses parçaları',
    subtitles: 'Altyazılar',
    chapters: 'Bölümler',
    thumbnails: 'Küçük resimler',
    heatmap: 'En çok izlenen yerler',
    heatmapHint: 'Yüksek sütunlar, izleyicilerin en çok geri sardığı anlar.',
    commands: 'Eşdeğer yt-dlp komutu',
    commandInspect: 'Bu incelemeyi terminalde tekrarlamak için',
    commandSuggested: 'En iyi video + orijinal ses indirmek için',
    noVideoFormats: 'Bu bağlantıda ayrı bir video parçası yok.',
    noAudioFormats: 'Bu bağlantıda ayrı bir ses parçası yok.',
    noSubtitles: 'Bu videoda hiç altyazı yok.',
    noChapters: 'Bu videoda bölüm işaretleri yok.',
    subManual: 'İnsan yazımı',
    subAuto: 'Otomatik oluşturulmuş',
    subAutoTranslated: 'Otomatik çeviri',
    subManualHelp: 'Bir kişi tarafından yüklenmiş altyazılar. Kalitesi genelde en yüksek olan bunlardır.',
    subAutoHelp:
      'YouTube’un konuşmayı tanıyarak videonun kendi dilinde ürettiği altyazı. Noktalama ve özel isimlerde hata yapar.',
    subAutoTranslatedHelp:
      'Otomatik altyazının makineyle başka bir dile çevrilmiş hâli. İki kat hata birikir; ciddi iş için güvenme.',
    subTranslatedCount: (n: number) => `${n} makine çevirisini göster`,
    subTranslatedHide: 'Makine çevirilerini gizle',
    subOriginalTrack: 'videonun kendi dili',
    subFrom: (lang: string) => `kaynak: ${lang}`,
    liveChat: 'Canlı sohbet kaydı da mevcut (altyazı değil, ayrı bir JSON dosyası).',
    playlistTitle: 'Bu bir liste',
    playlistBody: (n: number) =>
      `${n} video bulundu. Liste görünümünde kalite ve altyazı bilgisi yoktur — bir videoyu incelemek için satırına tıkla.`,
    playlistInspectEntry: 'Bu videoyu incele',
  },
  table: {
    format: 'Format',
    resolution: 'Çözünürlük',
    fps: 'FPS',
    codec: 'Kodek',
    dynamicRange: 'Renk',
    bitrate: 'Bit hızı',
    container: 'Kap',
    size: 'Boyut',
    language: 'Dil',
    channels: 'Kanal',
    sampleRate: 'Örnekleme',
    formats: 'Biçimler',
    name: 'Ad',
    duration: 'Süre',
    protocol: 'Aktarım',
    note: 'Not',
  },
  roles: {
    original: 'Orijinal',
    default: 'Varsayılan',
    dub: 'Dublaj',
    descriptive: 'Sesli betimleme',
    unknown: 'Ses',
  },
  roleHelp: {
    original:
      'Videonun asıl çekildiği dildeki ses. yt-dlp bunu language_preference=10 ile bildirir.',
    default: 'YouTube’un bu video için öntanımlı seçtiği ses. Orijinal olmak zorunda değil.',
    dub:
      'Başka bir dile seslendirilmiş parça. Dikkat: yt-dlp bunun insan seslendirmesi mi yoksa yapay zekâ dublajı mı olduğunu bildirmiyor — bu ayrımı yapmak mümkün değil.',
    descriptive: 'Görme engelliler için sahneleri anlatan ek anlatım içeren ses.',
    unknown: 'Bu videoda tek bir ses parçası var; site bir dil bilgisi vermiyor.',
  },
  terms: {
    hdr: {
      label: 'HDR',
      body:
        'Yüksek dinamik aralık. HDR10 ve Dolby Vision daha geniş renk ve parlaklık taşır ama eski ekranlarda soluk görünebilir. SDR her yerde doğru görünür.',
    },
    manifest: {
      label: 'akış',
      body:
        'Bu format tek bir dosya değil, parçalara bölünmüş bir akıştan (HLS/DASH) geliyor. Boyutu kesin bilinmez ve tahmin genelde olduğundan büyük çıkar.',
    },
    approxSize: {
      label: 'tahmini',
      body:
        'Kesin dosya boyutu bilinmiyor. Değer, bit hızı × süre ile hesaplandı; gerçek dosya bundan küçük olabilir.',
    },
    drm: {
      label: 'DRM',
      body:
        'İçerik kopya korumalı. Bu uygulama DRM korumasını aşmaz; bu formatlar indirilemez.',
    },
    muxed: {
      label: 'ses dahil',
      body:
        'Bu formatın içinde hem görüntü hem ses var. Ayrı ses parçası seçmene gerek kalmaz ama kalite seçeneği daha azdır.',
    },
    remux: {
      label: 'remux',
      body:
        'Yeniden kodlamadan, yalnızca kap (container) değiştirme. Hızlıdır ve kalite kaybı olmaz.',
    },
  },
  doctor: {
    title: 'Sistem durumu',
    subtitle: 'Uygulamanın dayandığı araçlar ve bu makinedeki yetenekleri.',
    refresh: 'Yeniden denetle',
    statusOk: 'Her şey yolunda',
    checkOk: 'Hazır',
    checkWarn: 'Eksik var',
    checkError: 'Sorun',
    statusWarn: 'Çalışıyor, ama eksikler var',
    statusError: 'Eksik bir bileşen var',
    checks: {
      yt_dlp: 'yt-dlp',
      js_runtime: 'JavaScript çalıştırıcı',
      ffmpeg: 'FFmpeg',
    },
    checkHelp: {
      yt_dlp: 'Siteleri çözümleyen ve indiren bileşen. YouTube sık değiştiği için güncel tutulmalı.',
      js_runtime:
        'YouTube, format listesini vermeden önce tarayıcıda JavaScript bulmacası çözdürüyor. Bunu çalıştıracak bir motor (deno veya node) olmazsa yt-dlp hata vermez ama bazı kaliteler listede hiç görünmez.',
      ffmpeg: 'Parçaları birleştiren, dönüştüren ve kesen araç.',
    },
    labels: {
      version: 'Sürüm',
      channel: 'Kanal',
      origin: 'Kaynak',
      package_version: 'Paket sürümü',
      ejs_version: 'yt-dlp-ejs',
      active: 'Kullanılan',
      found: 'Bulunanlar',
      ffmpeg_path: 'ffmpeg',
      ffprobe_path: 'ffprobe',
      capabilities: 'Yetenekler',
    },
    capabilities: {
      libx264: 'H.264 kodlama (libx264)',
      libx265: 'HEVC kodlama (libx265)',
      libsvtav1: 'AV1 kodlama (SVT-AV1)',
      videotoolbox_h264: 'H.264 donanım hızlandırma',
      videotoolbox_hevc: 'HEVC donanım hızlandırma',
      aac: 'AAC ses',
      libopus: 'Opus ses',
      libmp3lame: 'MP3 ses',
      flac: 'FLAC ses',
      webp: 'Animasyonlu WebP',
      gif: 'GIF',
      loudnorm: 'Ses seviyesi eşitleme (EBU R128)',
      palettegen: 'GIF için renk paleti',
      subtitles_filter: 'Altyazıyı görüntüye gömme (libass)',
    },
    missingExplained: {
      subtitles_filter:
        'Bu FFmpeg derlemesinde libass yok, bu yüzden altyazıyı görüntünün içine yakma özelliği kapalı. Altyazıyı dosyaya gömmek (soft subtitle) yine çalışıyor ve çoğu durumda daha iyidir.',
      webp:
        'Bu FFmpeg derlemesinde libwebp yok; animasyonlu WebP çıktısı üretilemez. GIF çıktısı çalışıyor.',
    },
    fixHint: 'Bunu düzeltmek için terminalde şunu çalıştır:',
    noFix: 'Düzeltme gerekmiyor.',
  },
  placeholder: {
    title: (name: string) => `${name} henüz hazır değil`,
    body: 'Bu bölüm sıradaki aşamalarda geliyor. Şimdilik İncele sekmesini kullanabilirsin.',
  },
  errors: {
    INVALID_URL: {
      title: 'Bu bir bağlantı değil',
      body: 'http:// veya https:// ile başlayan tam bir adres yapıştır.',
    },
    UNSUPPORTED_SITE: {
      title: 'Bu site desteklenmiyor',
      body: 'yt-dlp bu adres için bir çözümleyici bulamadı. Adresin doğru olduğundan emin ol.',
    },
    LOGIN_REQUIRED: {
      title: 'Giriş gerekiyor',
      body: 'Bu içerik hesap açmadan görünmüyor. Tarayıcı çerezleriyle giriş desteği sonraki aşamada geliyor.',
    },
    AGE_RESTRICTED: {
      title: 'Yaş kısıtlaması var',
      body: 'Bu videoyu görmek için giriş yapmış bir hesap gerekiyor.',
    },
    GEO_RESTRICTED: {
      title: 'Bu ülkede erişime kapalı',
      body: 'Site bu içeriği bulunduğun bölgeye sunmuyor.',
    },
    VIDEO_UNAVAILABLE: {
      title: 'Video yok',
      body: 'İçerik kaldırılmış, gizlenmiş veya adres yanlış.',
    },
    DRM_PROTECTED: {
      title: 'Kopya korumalı içerik',
      body: 'Bu içerik DRM ile korunuyor. Bu uygulama DRM korumasını aşmaz.',
    },
    LIVE_NOT_STARTED: {
      title: 'Yayın henüz başlamadı',
      body: 'Planlanmış bir yayın veya prömiyer. Başladıktan sonra tekrar dene.',
    },
    NO_JS_RUNTIME: {
      title: 'JavaScript çalıştırıcı bulunamadı',
      body: 'YouTube bulmacası çözülemedi, bu yüzden bazı kaliteler eksik olabilir. Sistem sekmesine bak.',
    },
    NETWORK: {
      title: 'Bağlantı kurulamadı',
      body: 'İnternet bağlantını kontrol edip tekrar dene.',
    },
    TIMEOUT: {
      title: 'Çözümleme çok uzun sürdü',
      body: 'Site yanıt vermedi. Tekrar denemek genelde işe yarar.',
    },
    UNKNOWN: {
      title: 'Beklenmeyen bir hata',
      body: 'Ham hata kaydını açıp ne olduğuna bakabilirsin.',
    },
  },
  warnings: {
    DRM_PRESENT: 'Bu videonun bazı formatları DRM korumalı ve indirilemez.',
    DRM_MAYBE: 'Bazı formatlar DRM korumalı olabilir; indirme sırasında başarısız olabilirler.',
    NO_AUDIO_LANGUAGE_INFO: 'Site ses parçaları için dil bilgisi vermiyor.',
    SIZES_ARE_ESTIMATES:
      'Bu sitede kesin dosya boyutu bilgisi yok; gösterilen bütün boyutlar tahmindir.',
    LIVE_CONTENT: 'Bu bir canlı yayın. Canlı yayın desteği sonraki aşamalarda geliyor.',
    PLAYLIST_TRACKS_NEED_PER_VIDEO_INSPECT:
      'Liste görünümü hızlı olsun diye kalite ve altyazı bilgisi çekilmedi.',
  },
  units: { bytes: 'B', kib: 'KB', mib: 'MB', gib: 'GB', tib: 'TB' },
} as const;

export type Strings = typeof tr;
