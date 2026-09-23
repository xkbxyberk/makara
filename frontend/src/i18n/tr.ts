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
    download: 'İndirmeler',
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
    views: (count: string) => `${count} görüntülenme`,
    subShadowed:
      'Aynı dilde insan yazımı altyazı da var; yt-dlp bu dili istediğinde her zaman onu verir.',
  },
  download: {
    title: 'İndir',
    submit: 'İndir',
    submitting: 'Kuyruğa ekleniyor…',
    shortcut: '⌘↵',
    queued: 'Kuyruğa eklendi.',
    openQueue: 'İndirmeleri aç',
    reinspect: 'Yeniden incele',
    showPicker: 'Parçaları seç',
    hidePicker: 'Parçaları gizle',
    planning: 'Hesaplanıyor…',
    willSaveTo: 'Kaydedileceği yer',
    estimatedSize: 'Tahmini boyut',
    unknownSize: 'boyut bilinmiyor',
    noVideo: 'Görüntü yok',
    noAudio: 'Ses yok',
    noSubtitles: 'Altyazı yok',
    subtitlesSummary: (list: string) => `Altyazı: ${list}`,
    moreTracks: (n: number) => `+${n}`,
    modes: {
      mkv: 'Arşiv MKV',
      compat_mp4: 'Uyumlu MP4',
      separate: 'Ayrı dosyalar',
      audio: 'Sadece ses',
    },
    modeHelp: {
      mkv: 'Seçtiğin her şey tek bir MKV dosyasında, dil etiketleriyle. Hiçbir şey yeniden kodlanmaz, kalite kaybı olmaz. QuickTime açmaz; IINA veya VLC ile oynat.',
      compat_mp4: 'QuickTime’da ve iPhone’da oynayan MP4 (H.264 + AAC). Kaynak uyumsuzsa yeniden kodlanır; bu yavaştır ve biraz kalite kaybettirir — öncesinde söylenir.',
      separate: 'Her parça ayrı dosya: görüntü, her ses dili, her altyazı. Oynatıcılar aynı adlı altyazıyı kendiliğinden yükler.',
      audio: 'Yalnızca ses, istediğin biçimde; kapak resmi ve bilgiler gömülü.',
    },
    sections: {
      video: 'Görüntü',
      audio: 'Ses',
      subtitles: 'Altyazılar',
      extras: 'Ekler',
      audioFormat: 'Ses biçimi',
      filename: 'Dosya adı',
      command: 'Eşdeğer yt-dlp komutu',
    },
    variant: 'Sürüm',
    extras: {
      thumbnail: 'Kapak resmini dosyaya göm',
      thumbnail_file: 'Kapak resmini ayrı dosya olarak kaydet',
      description: 'Açıklamayı metin dosyası olarak kaydet',
      info_json: 'Tüm bilgileri info.json olarak kaydet',
    },
    audioCodecs: {
      mp3: 'MP3 — her yerde çalar',
      m4a: 'M4A (AAC) — Apple için ideal',
      opus: 'Opus — en küçük dosya',
      flac: 'FLAC — kayıpsız',
      wav: 'WAV — sıkıştırmasız',
    },
    quality: 'Kalite',
    qualityBest: 'En iyi',
    templateHelp:
      'yt-dlp şablon dili. %(title)s başlık, %(channel)s kanal, %(upload_date>%Y-%m-%d)s tarih, %(id)s video kimliği. / işareti klasör açar.',
    templateReset: 'Varsayılana dön',
    translatedFilter: 'Dil ara…',
    notices: {
      MKV_PLAYERS: 'MKV dosyalarını QuickTime ve iPhone Fotoğraflar açmaz. IINA, VLC veya Infuse ile oynat.',
      AV1_HARDWARE: 'Seçilen görüntü AV1. M3 ve sonrası Mac’lerde, A17 Pro ve sonrası iPhone’larda donanımla oynar; eski cihazlarda işlemciyi yorar.',
      VIDEO_REENCODE: (p: { codec?: string }) =>
        `${p.codec ?? 'Bu'} görüntü QuickTime’da oynamaz; H.264’e yeniden kodlanacak. Bu yavaştır ve biraz kalite kaybettirir.`,
      COMPATIBLE_ALTERNATIVE: (p: { height?: number; format_id?: string }) =>
        `Yeniden kodlamadan kaçınmak için doğrudan uyumlu olan ${p.height ?? ''}p H.264 sürümünü seçebilirsin.`,
      HDR_TONEMAP: 'HDR görüntü SDR’a çevrilirken renkler soluk görünebilir (bu FFmpeg’de ton eşleme sınırlı).',
      AUDIO_REENCODE: (p: { codec?: string }) =>
        `${p.codec ?? 'Bu'} ses AAC’ye çevrilecek (hızlıdır, fark duyulmaz).`,
      MP4_MULTI_AUDIO: 'MP4’te birden çok ses dili var: QuickTime aralarında geçiş yapabilir, iPhone ilkini çalar.',
      SILENT_VIDEO: 'Hiç ses seçilmedi; dosya sessiz olacak.',
      NO_VIDEO_SELECTED: 'Bir görüntü seç.',
      NO_AUDIO_SELECTED: 'Bir ses parçası seç.',
      AUDIO_MODE_ONE_TRACK: 'Sadece ses modunda tek bir ses parçası seçilebilir.',
      UNKNOWN_AUDIO_CODEC: 'Bir ses biçimi seç.',
      WAV_NO_COVER: 'WAV dosyalarına kapak resmi gömülemez.',
      DRM_MAYBE_SELECTED: 'Seçilen parçalardan biri DRM korumalı olabilir; indirme başarısız olabilir.',
      MACHINE_TRANSLATED_SUBS: 'Makine çevirisi altyazı seçtin; hatalar içerebilir.',
      UNKNOWN_SELECTION: 'Seçimde artık bulunmayan bir parça var. Yeniden incele.',
      CODEC_UNKNOWN:
        'Bu site kodek bilgisi vermiyor. Dosya indirildikten sonra incelenecek; QuickTime’da oynamayacaksa yeniden kodlanacak.',
      AUDIO_MODE_COPY: (p: { codec?: string }) =>
        `${p.codec ?? 'Ses'} olduğu gibi kopyalanacak — kalite kaybı yok, kalite seçimi uygulanmaz.`,
      AUDIO_MODE_REENCODE: (p: { codec?: string; target?: string }) =>
        `${p.codec ?? 'Ses'} → ${String(p.target ?? '').toUpperCase()} yeniden kodlanacak. Kayıplı bir biçimden diğerine geçiş küçük bir kalite kaybı demektir.`,
      LOSSLESS_FROM_LOSSY: (p: { codec?: string }) =>
        `Kaynak ${p.codec ?? 'kayıplı'}; kayıpsız biçime çevirmek kaybolan kaliteyi geri getirmez, yalnızca dosyayı büyütür.`,
    } as Record<string, string | ((p: Record<string, unknown>) => string)>,
  },
  queue: {
    title: 'İndirmeler',
    emptyTitle: 'Henüz indirme yok',
    emptyBody: 'İncele sekmesinde bir bağlantı açıp İndir’e bastığında işler burada görünür.',
    loading: 'Kuyruk yükleniyor',
    reconnecting: 'Sunucuyla bağlantı koptu; yeniden bağlanılıyor…',
    cancel: 'İptal et',
    retry: 'Tekrar dene',
    remove: 'Listeden kaldır',
    removeHelp: 'Yalnızca listeden kaldırır; indirilen dosyalar silinmez.',
    reveal: 'Finder’da göster',
    item: (i: number, n: number) => `${i}/${n}`,
    eta: (text: string) => `${text} kaldı`,
    speed: (text: string) => `${text}/s`,
    activeCount: (n: number) => `${n}`,
    statuses: {
      queued: 'Sırada',
      running: 'Çalışıyor',
      done: 'Tamamlandı',
      failed: 'Başarısız',
      cancelled: 'İptal edildi',
    } as Record<string, string>,
    stages: {
      queued: 'Sırada bekliyor',
      starting: 'Başlıyor',
      preparing: 'Hazırlanıyor',
      downloading: 'İndiriliyor',
      postprocessing: 'İşleniyor',
      merging: 'Birleştiriliyor',
      converting: 'Dönüştürülüyor',
      cancelling: 'İptal ediliyor',
      done: 'Tamamlandı',
      failed: 'Başarısız',
      cancelled: 'İptal edildi',
    } as Record<string, string>,
    warnings: {
      SUBTITLE_SKIPPED: (key: string) =>
        `“${key}” altyazısı FFmpeg’in okuyamadığı bir biçimde geldi; dosyaya eklenmedi.`,
    } as Record<string, (key: string) => string>,
    notifyDone: 'İndirme tamamlandı',
    notifyFailed: 'İndirme başarısız',
  },
  library: {
    title: 'Kütüphane',
    search: 'Başlık veya kanal ara',
    grid: 'Izgara',
    list: 'Liste',
    view: 'Görünüm',
    sortLabel: 'Sırala',
    sorts: {
      added: 'Eklenme tarihi',
      uploaded: 'Yayın tarihi',
      title: 'Başlık',
      size: 'Boyut',
      duration: 'Süre',
    } as Record<string, string>,
    allSites: 'Tüm siteler',
    kinds: { all: 'Tümü', video: 'Video', audio: 'Ses' } as Record<string, string>,
    kindLabel: 'Tür',
    siteLabel: 'Site',
    onlyMissing: 'Yalnızca eksikler',
    scan: 'Dosyaları denetle',
    scanning: 'Denetleniyor…',
    scanResult: (c: { checked: number; missing: number; repaired: number; restored: number }) =>
      `${c.checked} öğe denetlendi · ${c.repaired} dosyanın yeni yeri bulundu · ${c.restored} geri geldi · ${c.missing} eksik`,
    summary: (count: number, size: string, missing: number) =>
      missing ? `${count} öğe · ${size} · ${missing} eksik` : `${count} öğe · ${size}`,
    loading: 'Kütüphane yükleniyor',
    emptyTitle: 'Kütüphane boş',
    emptyBody: 'Bitirdiğin her indirme burada, bilgileriyle birlikte listelenir.',
    noMatchTitle: 'Eşleşen öğe yok',
    noMatchBody: 'Aramayı veya filtreleri değiştir.',
    missing: 'Eksik',
    missingHelp:
      'Dosya kaydedildiği yerde yok. Finder’da taşındıysa “Dosyaları denetle” aynı boyut ve süreye sahip dosyayı bulup bağlantıyı düzeltir. Kayıt hiçbir zaman kendiliğinden silinmez.',
    play: 'Oynat',
    playHelp: 'Varsayılan oynatıcıda açar (IINA, QuickTime…).',
    reveal: 'Finder’da göster',
    trash: 'Çöp Kutusu’na taşı',
    trashTitle: 'Çöp Kutusu’na taşınsın mı?',
    trashBody: (n: number) =>
      n === 1
        ? 'Bu dosya Çöp Kutusu’na taşınacak. Çöp Kutusu’nu boşaltana kadar geri alabilirsin.'
        : `Bu öğenin ${n} dosyası Çöp Kutusu’na taşınacak. Çöp Kutusu’nu boşaltana kadar geri alabilirsin.`,
    confirmTrash: 'Çöp Kutusu’na taşı',
    cancel: 'Vazgeç',
    details: 'Ayrıntılar',
    source: 'Kaynak',
    files: 'Dosyalar',
    audioTracks: 'Ses',
    subtitleTracks: 'Altyazı',
    added: 'Eklendi',
    noTracks: '–',
    video: 'Görüntü',
  },
  settings: {
    title: 'Ayarlar',
    save: 'Kaydet',
    saved: 'Kaydedildi.',
    unsaved: 'Kaydedilmemiş değişiklikler var.',
    loading: 'Ayarlar yükleniyor',
    downloadDir: 'İndirme klasörü',
    downloadDirHelp: 'Bütün indirmeler bu klasörün içine, aşağıdaki şablona göre yerleşir.',
    chooseFolder: 'Seç…',
    choosePrompt: 'İndirmelerin kaydedileceği klasörü seç',
    template: 'Dosya adı şablonu',
    templatePreview: 'Örnek',
    templateReset: 'Varsayılana dön',
    sample: {
      title: 'Örnek video başlığı',
      channel: 'Örnek Kanal',
      id: 'dQw4w9WgXcQ',
      extractor_key: 'Youtube',
      upload_date: '20260923',
    },
    concurrency: 'Aynı anda indirme',
    concurrencyHelp:
      'Aynı anda kaç indirme çalışsın. Yüksek değer bağlantını paylaştırır; sitelerin hız sınırına takılma riski artar.',
    defaultMode: 'Varsayılan çıktı',
    theme: 'Görünüm',
    themes: { system: 'Sistem', light: 'Açık', dark: 'Koyu' } as Record<string, string>,
    clipboard: 'Pano izleyici',
    clipboardHelp:
      'Uygulama açıkken desteklenen bir bağlantı kopyaladığında incelemeyi önerir. Pano yalnızca içeriği değiştiğinde okunur.',
    notifications: 'Sistem bildirimleri',
    notificationsHelp: 'Pencere arka plandayken bir indirme bitince veya başarısız olunca bildirim gösterir.',
  },
  clipboard: {
    offer: 'Panoya bir bağlantı kopyaladın:',
    inspect: 'İncele',
    dismiss: 'Yoksay',
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
    unknown:
      'Bu videoda tek bir ses dili var. Karşılaştırılacak başka parça olmadığı için orijinal mi dublaj mı olduğu bilinmiyor.',
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
    format: {
      label: 'Format',
      body: 'yt-dlp’nin bu parçaya verdiği kimlik. Aynı video farklı kalite ve kodeklerde birden çok format olarak sunulur.',
    },
    fps: {
      label: 'FPS',
      body: 'Saniyedeki kare sayısı. 60 FPS hareketi daha akıcı gösterir; dosya biraz büyür.',
    },
    codec: {
      label: 'Kodek',
      body: 'Görüntünün veya sesin sıkıştırılma yöntemi. Aynı kalitede AV1 en küçük, H.264 en uyumlu olandır.',
    },
    bitrate: {
      label: 'Bit hızı',
      body: 'Saniyede kullanılan veri miktarı. Aynı kodekte daha yüksek bit hızı genelde daha iyi kalite ve daha büyük dosya demektir.',
    },
    container: {
      label: 'Kap',
      body: 'Parçaları taşıyan dosya türü (mp4, webm, mkv). Kodekten farklıdır: aynı görüntü farklı kaplara konabilir.',
    },
    sampleRate: {
      label: 'Örnekleme',
      body: 'Sesin saniyede kaç kez ölçüldüğü. 44,1 ve 48 kHz ikisi de CD kalitesi veya üstüdür.',
    },
    channels: {
      label: 'Kanal',
      body: 'Ses kanalı sayısı: 1 mono, 2 stereo, 6 ise 5.1 çevresel ses.',
    },
    aiUpscaled: {
      label: 'YZ ile büyütülmüş',
      body: 'YouTube bu çözünürlüğü yapay zekâ ile daha düşük çözünürlüklü orijinalden üretmiş. Daha net görünebilir ama gerçek bir kayıt değildir; arşiv için orijinal seçilir.',
    },
    drc: {
      label: 'DRC',
      body: 'Dinamik aralığı sıkıştırılmış ses: sessiz ve yüksek yerler birbirine yaklaştırılmış. Telefon hoparlöründe rahat duyulur ama orijinal değildir.',
    },
    partialSize: {
      label: 'en az',
      body: 'Seçtiğin parçaların bazılarının boyutu bilinmiyor; gösterilen değer yalnızca bilinenlerin toplamı.',
    },
    remux: {
      label: 'remux',
      body:
        'Yeniden kodlamadan, yalnızca kap (container) değiştirme. Hızlıdır ve kalite kaybı olmaz.',
    },
  },
  codecs: {
    'H.264': 'En yaygın video kodeği. Her Mac, iPhone ve tarayıcıda oynar; aynı kalite için AV1 ve VP9’dan daha büyük dosya üretir.',
    HEVC: 'H.265. H.264’ün yaklaşık yarı boyutunda aynı kalite. Apple cihazlarında oynar, bazı tarayıcılarda oynamaz.',
    AV1: 'En yeni ve en verimli video kodeği. Donanımla çözme M3 ve sonrası Mac’lerde, A17 Pro ve sonrası iPhone’larda var; eskilerde işlemciyi yorar.',
    VP9: 'Google’ın video kodeği. Tarayıcılarda ve VLC/IINA’da oynar; QuickTime ve iPhone Fotoğraflar açmaz.',
    'Dolby Vision': 'Dolby’nin HDR biçimi. Desteklemeyen ekran ve oynatıcılarda renkler yanlış görünebilir.',
    AAC: 'En uyumlu ses kodeği. Apple cihazlarının hepsinde oynar.',
    Opus: 'Aynı bit hızında AAC’den daha iyi ses kalitesi veren modern kodek. QuickTime ve iPhone’da MP4 içinde oynamaz.',
  } as Record<string, string>,
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
    updateYtdlp: 'yt-dlp’yi güncelle',
    updating: 'Güncelleniyor… (bir dakika sürebilir)',
    updated: (from: string, to: string) => `yt-dlp ${from} → ${to} güncellendi.`,
    upToDate: (version: string) => `yt-dlp zaten güncel (${version}).`,
    updateHelp:
      'YouTube sık değişir; indirmeler bozulursa ilk yapılacak şey budur. Kilit dosyasını günceller, böylece güncelleme kalıcı olur.',
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
    BOT_CHECK: {
      title: 'YouTube bot doğrulaması istedi',
      body: 'Video herkese açık, ama YouTube bu bağlantıyı şüpheli buldu. Biraz bekleyip tekrar dene; sürerse tarayıcı çerezleriyle giriş (sonraki aşama) çözer.',
    },
    RATE_LIMITED: {
      title: 'Çok fazla istek',
      body: 'Site istekleri geçici olarak sınırladı. Birkaç dakika bekleyip tekrar dene.',
    },
    FORBIDDEN: {
      title: 'Site erişimi reddetti',
      body: 'Bu genelde yt-dlp’nin eskidiği anlamına gelir. Sistem sekmesinden yt-dlp’yi güncelle ve tekrar dene.',
    },
    INSPECT_EXPIRED: {
      title: 'İnceleme bilgisi eskidi',
      body: 'Uygulama yeniden başladığı için bu videonun bilgileri kayboldu. Yeniden inceleyip tekrar dene.',
    },
    SELECTION_INVALID: {
      title: 'Seçim eksik',
      body: 'İndirmeden önce yukarıdaki uyarılara bak.',
    },
    INVALID_TEMPLATE: {
      title: 'Dosya adı şablonu geçersiz',
      body: 'Şablonda kapanmamış bir %( ) alanı olabilir, ya da / veya ~ ile başlıyor olabilir.',
    },
    PATH_OUTSIDE_ROOT: {
      title: 'İndirme klasörünün dışına yazılamaz',
      body: 'Şablon ../ içeriyor. Dosyalar her zaman indirme klasörünün içine kaydedilir.',
    },
    PATH_EXHAUSTED: {
      title: 'Uygun bir dosya adı bulunamadı',
      body: 'Aynı adla çok fazla dosya var. Şablonu değiştir.',
    },
    DOWNLOAD_DIR_UNSAFE: {
      title: 'Bu klasör indirme için kullanılamaz',
      body: 'Diskin kökü veya bir sistem klasörü seçilemez. Filmler veya Belgeler altında bir klasör seç.',
    },
    DOWNLOAD_DIR_NOT_ABSOLUTE: {
      title: 'İndirme klasörü tam yol olmalı',
      body: '/ veya ~ ile başlayan bir klasör seç.',
    },
    FFMPEG_FAILED: {
      title: 'FFmpeg dosyayı oluşturamadı',
      body: 'Ham hata kaydına bak. Farklı bir çıktı modu denemek genelde işe yarar.',
    },
    DISK_FULL: {
      title: 'Disk dolu',
      body: 'Yer açıp tekrar dene; yarım kalan indirme kaldığı yerden devam eder.',
    },
    DOWNLOAD_INCOMPLETE: {
      title: 'İndirme tamamlanmadı',
      body: 'Bir parça eksik kaldı. Tekrar dene; kaldığı yerden devam eder.',
    },
    WORKER_CRASHED: {
      title: 'İndirme işlemi beklenmedik biçimde durdu',
      body: 'Ham hata kaydına bak ve tekrar dene.',
    },
    WORKER_START_FAILED: {
      title: 'İndirme başlatılamadı',
      body: 'Python ortamında bir sorun var. Sistem sekmesine bak.',
    },
    JOB_NOT_FOUND: { title: 'İş bulunamadı', body: 'Bu iş listeden kaldırılmış olabilir.' },
    JOB_NOT_REMOVABLE: {
      title: 'Çalışan iş kaldırılamaz',
      body: 'Önce iptal et, sonra listeden kaldır.',
    },
    FILE_MISSING: {
      title: 'Dosya yerinde değil',
      body: 'Finder’da taşınmış veya silinmiş olabilir.',
    },
    ITEM_NOT_FOUND: { title: 'Öğe bulunamadı', body: 'Kütüphaneden kaldırılmış olabilir.' },
    PICKER_UNAVAILABLE: {
      title: 'Klasör seçici açılamadı',
      body: 'Klasör yolunu elle yazabilirsin.',
    },
    UPDATE_UNAVAILABLE: {
      title: 'Güncelleme bu modda kapalı',
      body: 'Test modunda Python ortamına dokunulmaz.',
    },
    UPDATE_FAILED: {
      title: 'Güncelleme başarısız',
      body: 'Ham kayda bak. İnternet bağlantısı gerekir.',
    },
    FORBIDDEN_ORIGIN: {
      title: 'İstek reddedildi',
      body: 'Bu istek uygulamanın kendi penceresinden gelmedi.',
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
    NO_JS_RUNTIME:
      'JavaScript çalıştırıcı bulunamadı; YouTube’un bazı kaliteleri bu listede hiç görünmüyor olabilir. Sistem sekmesine bak.',
    FORMATS_MAY_BE_MISSING:
      'yt-dlp YouTube’un imza bulmacasını çözemedi; bazı kaliteler eksik. Genelde yt-dlp’yi güncellemek düzeltir.',
  },
  units: {
    bytes: 'B',
    kib: 'KB',
    mib: 'MB',
    gib: 'GB',
    tib: 'TB',
    kbps: 'kbps',
    mbps: 'Mbps',
    khz: 'kHz',
    fps: 'fps',
  },
} as const;

export type Strings = typeof tr;
