/**
 * Every user-facing string in the app lives here, and nowhere else.
 * The backend only ever returns codes; this file turns them into Turkish.
 * Adding English later means adding one sibling file and a language switch.
 */
export const tr = {
  app: {
    name: 'VideoDownloader',
    brand: 'Medya',
    systemSection: 'Uygulama',
    themeToggle: 'Temayı değiştir',
    theme: 'Tema',
    showSidebar: 'Kenar çubuğunu göster',
    hideSidebar: 'Kenar çubuğunu gizle',
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
    quick: {
      title: 'Hızlı seçim',
      videoHelp: 'Videonun sunduğu her kalite, orijinal sesle. Dil ve altyazı için: Parçaları seç.',
      audioHelp: 'Yalnızca ses: kaynağın kendi akışları ve dönüştürmeler.',
      copy: 'Yeniden kodlamasız',
      transcode: 'Dönüştürülür',
      probe: 'Gerekirse dönüştürülür',
      sizeLater: 'boyut dönüştürünce belli olur',
      unknownHeight: 'Kalite bilinmiyor',
      fps: (fps: number) => `${fps} fps`,
      remembered: 'bu sitede son seçimin',
      formats: { m4a: 'M4A (AAC)', opus: 'Opus', mp3: 'MP3' } as Record<'m4a' | 'opus' | 'mp3', string>,
    },
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
      studio: 'Stüdyo',
    } as Record<string, string>,
    modeHelp: {
      mkv: 'Seçtiğin her şey tek bir MKV dosyasında, dil etiketleriyle. Hiçbir şey yeniden kodlanmaz, kalite kaybı olmaz. QuickTime açmaz; IINA veya VLC ile oynat.',
      compat_mp4: 'QuickTime’da ve iPhone’da oynayan MP4 (H.264 + AAC). Kaynak uyumsuzsa yeniden kodlanır; bu yavaştır ve biraz kalite kaybettirir — öncesinde söylenir.',
      separate: 'Her parça ayrı dosya: görüntü, her ses dili, her altyazı. Oynatıcılar aynı adlı altyazıyı kendiliğinden yükler.',
      audio: 'Yalnızca ses, istediğin biçimde; kapak resmi ve bilgiler gömülü.',
      studio: 'Stüdyo’da bir kaynaktan üretilmiş yeni dosya. Kaynağa dokunulmaz.',
    } as Record<string, string>,
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
    usedSession: 'Safari oturumuyla',
    usedSessionHelp: 'Bu video giriş istediği için Safari’deki YouTube oturumunla indiriliyor.',
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
      processing: 'İşleniyor',
      finalizing: 'Dosyalar yerleştiriliyor',
      retrying: 'Site reddetti, yeniden deneniyor',
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
    scanHelp:
      'Her öğenin dosyasının hâlâ yerinde olduğuna bakar. Finder’da taşınan dosyayı aynı boyut ve süreyle bulup bağlantıyı düzeltir; bulamadıklarını “Eksik” diye işaretler.',
    catalogueFailed: 'Bir indirme tamamlandı ama kütüphaneye eklenemedi. Dosya diskte duruyor.',
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
    openInStudio: 'Stüdyo’da aç',
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
    safariLogin: 'Giriş isteyen videolarda Safari oturumunu kullan',
    safariLoginHelp:
      'Yaş kısıtlı ya da yalnızca üyelere açık bir video önce her zamanki gibi oturumsuz denenir; site giriş isterse Safari’deki YouTube oturumunla bir kez daha denenir. Uygulamanın Tam Disk Erişimi olmalı. yt-dlp’nin uyarısı: hesapla indirmek, hesabın geçici ya da kalıcı kapatılması riskini taşır; bu yüzden oturum yalnızca gereken videolarda kullanılır.',
  },
  studio: {
    title: 'Stüdyo',
    operation: 'İşlem',
    source: 'Kaynak',
    fromLibrary: 'Kütüphaneden seç…',
    pathLabel: 'Dosya yolu',
    pathPlaceholder: 'Bir video, ses veya altyazı dosyasının tam yolu',
    chooseFile: 'Dosya seç…',
    choosePrompt: 'Stüdyo’da açılacak dosyayı seç',
    open: 'Aç',
    emptyTitle: 'Bir kaynak seç',
    emptyBody:
      'Kütüphanedeki bir öğeyi ya da Mac’indeki herhangi bir dosyayı aç. Stüdyo kaynağa asla dokunmaz; her işlem yanına yeni bir dosya yazar.',
    probing: 'Dosya inceleniyor',
    sourceSummary: (duration: string, streams: string) => `${duration} · ${streams}`,
    streamKinds: { video: 'görüntü', audio: 'ses', subtitle: 'altyazı' } as Record<string, string>,
    tabs: { audio: 'Ses', trim: 'Kes', remux: 'Remux ve izler', subtitle: 'Altyazı' } as Record<string, string>,
    output: 'Çıktı adı',
    outputSuffix: {
      audio: '(ses)',
      trim: '(kesit)',
      remux: '(remux)',
      subtitle: '(altyazı)',
    } as Record<string, string>,
    willWrite: 'Yazılacak dosya',
    commands: 'Çalıştırılacak komutlar',
    run: 'Çalıştır',
    queued: 'Kuyruğa eklendi.',
    openQueue: 'İndirmeleri aç',
    planning: 'Hesaplanıyor…',
    steps: {
      WRITE_CONCAT_LIST: 'Parçaların listesi yazılır (FFmpeg birleştirme listesi).',
      SHIFT: 'Altyazı zamanları kaydırılır (uygulama içinde, SRT olarak).',
      CLEAN_CAPTIONS:
        'YouTube otomatik altyazısındaki tekrar eden satırlar temizlenir (uygulama içinde, SRT olarak).',
      LOUDNESS_MEASURE: '1. geçiş: ses seviyesi ölçülür.',
      LOUDNESS_APPLY: '2. geçiş: ölçüme göre düzeltilir ({LOUDNORM_MEASURED} yerine 1. geçişin değerleri gelir).',
    } as Record<string, string>,
    audio: {
      codec: 'Biçim',
      bitrate: 'Bit hızı',
      sampleRate: 'Örnekleme',
      channels: 'Kanal',
      auto: 'Kaynaktaki gibi',
      mono: 'Mono',
      stereo: 'Stereo',
      track: 'Ses izi',
      loudnorm: 'Ses seviyesini eşitle',
    },
    trim: {
      mode: 'Kesim türü',
      lossless: 'Kayıpsız',
      accurate: 'Kare hassas',
      segments: 'Parçalar',
      start: 'Başlangıç',
      end: 'Bitiş',
      addSegment: 'Parça ekle',
      removeSegment: 'Kaldır',
      join: 'Parçaları tek dosyada birleştir',
      chapters: 'Bölümlerden ekle',
      timeHelp: 'Saniye ya da dk:sn biçiminde: 90, 1:30, 1:02:03.5',
    },
    remux: {
      container: 'Kap',
      keep: 'Tut',
      kind: 'Tür',
      codec: 'Kodek',
      language: 'Dil',
      title: 'Başlık',
      isDefault: 'Varsayılan',
      moveUp: 'Yukarı taşı',
      moveDown: 'Aşağı taşı',
      addFile: 'Dosya ekle (ses veya altyazı)…',
      addPath: 'Eklenecek dosyanın yolu',
      add: 'Ekle',
      fromExtra: (name: string) => `ek: ${name}`,
      languagePlaceholder: 'tr, en…',
    },
    subtitle: {
      action: 'İşlem',
      actions: {
        convert: 'Biçim dönüştür',
        shift: 'Zamanı kaydır',
        clean: 'YouTube otomatik altyazısını temizle',
      } as Record<string, string>,
      target: 'Hedef biçim',
      offset: 'Kaydırma (sn, eksi = erken)',
      offsetInvalid: 'Bir sayı gir, örneğin 1,5 ya da -2.',
      looksAuto: 'Bu dosya YouTube otomatik altyazısına benziyor; “temizle” önerilir.',
    },
    notices: {
      LOUDNESS_TWO_PASS: (p: { target?: number }) =>
        `Ses iki geçişte ${p.target ?? -16} LUFS’a eşitlenecek (EBU R128): önce ölçülür, sonra doğrusal olarak düzeltilir.`,
      LOSSLESS_FROM_LOSSY: (p: { codec?: string }) =>
        `Kaynak ${p.codec ?? 'kayıplı'}; kayıpsız biçime çevirmek kaybolan kaliteyi geri getirmez, yalnızca dosyayı büyütür.`,
      NO_AUDIO_IN_SOURCE: 'Bu dosyada ses yok.',
      INVALID_SEGMENT: (p: { start?: number; end?: number }) =>
        `Geçersiz parça (${p.start ?? '?'} → ${p.end ?? '?'} sn): bitiş başlangıçtan sonra ve dosyanın içinde olmalı.`,
      NO_SEGMENTS: 'En az bir parça ekle.',
      SEGMENTS_SEPARATE: (p: { count?: number }) =>
        `${p.count ?? 'Birkaç'} ayrı dosya yazılacak. Tek dosya için “birleştir”i işaretle.`,
      LOSSLESS_KEYFRAMES:
        'Kayıpsız kesim yeniden kodlamaz ve anında biter, ama yalnızca anahtar karelerde kesebilir: başlangıç en yakın önceki anahtar kareye kayar, bitiş birkaç kare uzun olabilir.',
      CUT_MOVES_TO_KEYFRAME: (p: { requested?: number; actual?: number }) =>
        `Başlangıç ${p.requested} sn yerine ${p.actual} sn olacak (en yakın anahtar kare). Tam an için “Kare hassas”ı seç.`,
      ACCURATE_REENCODES:
        'Kare hassas kesim tam istediğin karede keser ama görüntüyü yeniden kodlar (H.264): daha yavaştır, gözle görülmeyecek kadar az kalite kaybı olur.',
      JOIN_FIRST_TRACKS_ONLY:
        'Kare hassas birleştirmede yalnızca ilk görüntü ve ilk ses izi korunur.',
      SUBTITLE_NOT_IN_MP4: (p: { codec?: string }) =>
        `${p.codec ?? 'Bu'} altyazısı resim tabanlı; MP4’e konamaz. MKV seç ya da izi kaldır.`,
      CODEC_NOT_IN_MP4: (p: { codec?: string }) =>
        `${p.codec ?? 'Bu'} izi MP4’e yeniden kodlanmadan konamaz. MKV seç ya da izi kaldır.`,
      NO_TRACKS_KEPT: 'En az bir iz tut.',
      UNKNOWN_TRACK: 'Listede artık bulunmayan bir iz var.',
      REMUX_NO_REENCODE:
        'Remux yeniden kodlamaz: izler olduğu gibi kopyalanır, yalnızca kap ve iz bilgileri değişir. Hızlıdır, kalite kaybı yoktur.',
      NOT_A_SUBTITLE: 'Bu dosya bir altyazı değil.',
      ASS_STYLING_LOST: 'ASS’teki yazı tipi ve renk bilgileri bu işlemde kaybolur (sonuç SRT tabanlıdır).',
      OPUS_48K: 'Opus 44,1 kHz desteklemez; çıktı 48 kHz olacak.',
      JOIN_DROPS_COVER: 'Kayıpsız birleştirmede kapak resmi korunamaz; birleştirilmiş dosya kapaksız olur.',
      ACCURATE_AUDIO_REENCODES:
        'Kare hassas kesim sesi aynı biçimde yeniden kodlar (FLAC ve WAV kayıpsız kalır).',
      LEGACY_ENCODING: (p: { charset?: string }) =>
        `Bu altyazı eski bir kodlamada (${p.charset ?? '?'}); Türkçe karakterler doğru okunacak ve çıktı UTF-8 olacak.`,
    } as Record<string, string | ((p: Record<string, unknown>) => string)>,
    terms: {
      lossless: {
        label: 'Kayıpsız',
        body: 'Görüntü yeniden kodlanmaz, kopyalanır: anında biter ve kalite kaybı olmaz, ama kesim yalnızca anahtar karelerde olabilir.',
      },
      accurate: {
        label: 'Kare hassas',
        body: 'Tam istediğin karede keser. Bunun için görüntüyü yeniden kodlar: daha yavaş, çok az kalite kaybı.',
      },
      keyframe: {
        label: 'anahtar kare',
        body: 'Kendi başına çözülebilen tam kare. Aradaki kareler yalnızca farkları taşır; bu yüzden kopyalayarak yapılan kesim ancak anahtar karelerde başlayabilir.',
      },
      loudnorm: {
        label: 'EBU R128',
        body: 'Yayın standardı ses yüksekliği ölçümü. Parçaları aynı algılanan seviyeye (-16 LUFS, podcast’lerin kullandığı değer) getirir; bölümler arasında ses açıp kısmak gerekmez.',
      },
      remux: {
        label: 'Remux',
        body: 'Yeniden kodlamadan kap (container) değiştirme ve izleri düzenleme. Hızlıdır ve kalite kaybı olmaz.',
      },
      container: {
        label: 'Kap',
        body: 'MKV her şeyi taşır ama QuickTime açmaz; MP4/MOV Apple cihazlarında oynar ama bazı ses ve altyazı türlerini kabul etmez.',
      },
    },
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
      safari_session: 'Safari oturumu',
    },
    checkHelp: {
      yt_dlp: 'Siteleri çözümleyen ve indiren bileşen. YouTube sık değiştiği için güncel tutulmalı.',
      js_runtime:
        'YouTube, format listesini vermeden önce tarayıcıda JavaScript bulmacası çözdürüyor. Bunu çalıştıracak bir motor (deno veya node) olmazsa yt-dlp hata vermez ama bazı kaliteler listede hiç görünmez.',
      ffmpeg: 'Parçaları birleştiren, dönüştüren ve kesen araç.',
      safari_session:
        'Yaş kısıtlı ve giriş isteyen videolar için Safari’deki YouTube oturumun. Yalnızca çerezlerin adlarına bakılır (giriş yapılmış mı diye); değerleri hiçbir yerde gösterilmez ya da kaydedilmez.',
    },
    sessionStates: {
      off: 'Kapalı: giriş isteyen videolar oturumsuz denenir ve “giriş gerekiyor” der. Ayarlar’dan açılabilir.',
      unavailable: 'Safari’nin çerez dosyası bulunamadı. Safari’yi bir kez açıp YouTube’a giriş yap.',
      no_access:
        'Uygulama Safari oturumunu okuyamıyor: macOS bunun için Tam Disk Erişimi istiyor. Sistem Ayarları > Gizlilik ve Güvenlik > Tam Disk Erişimi’nde VideoDownloader’ı açıp uygulamayı yeniden başlat. (Sunucuyu Terminal’den başlattıysan izin Terminal’e verilmeli.)',
      signed_out: 'Safari’de YouTube’a giriş yapılmamış. Yaş kısıtlı videolar için Safari’de YouTube’a giriş yap.',
      signed_in: 'Hazır: Safari’de YouTube’a giriş yapılmış. Yalnızca giriş isteyen videolarda kullanılır.',
      unknown: 'Safari oturumu okunabiliyor; YouTube’a giriş yapılıp yapılmadığı anlaşılamadı.',
    } as Record<string, string>,
    openFullDiskAccess: 'Tam Disk Erişimi ayarlarını aç',
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
      body: 'Uygulama bir kez kendiliğinden yeniden denedi. Bu çoğu zaman geçicidir: birkaç dakika sonra “Tekrar dene”. Sürerse Sistem sekmesinden yt-dlp’yi güncelle.',
    },
    COOKIES_UNREADABLE: {
      title: 'Safari oturumu okunamadı',
      body: 'Bu video giriş istiyor ama uygulama Safari oturumunu okuyamıyor. Sistem Ayarları > Gizlilik ve Güvenlik > Tam Disk Erişimi’nde VideoDownloader’ı açıp uygulamayı yeniden başlat (Sistem ekranında kısayolu var).',
    },
    SESSION_NOT_ENOUGH: {
      title: 'Oturumla da açılmadı',
      body: 'Video Safari’deki oturumunla denendi ama yine giriş istendi. Safari’de YouTube’a giriş yapılmış mı, hesabın yaşı doğrulanmış mı? Sistem ekranındaki “Safari oturumu” satırına bak.',
    },
    SETTINGS_UNAVAILABLE: {
      title: 'Sistem Ayarları açılamadı',
      body: 'Sistem Ayarları > Gizlilik ve Güvenlik > Tam Disk Erişimi’ne elle git.',
    },
    INSPECT_EXPIRED: {
      title: 'İnceleme bilgisi eskidi',
      body: 'Uygulama yeniden başladığı için bu videonun bilgileri kayboldu. Yeniden inceleyip tekrar dene.',
    },
    OFFER_UNKNOWN: {
      title: 'Bu seçenek bu videoda yok',
      body: 'Seçtiğin kalite bu videoda bulunmuyor. Sayfayı yeniden inceleyip listeden seç.',
    },
    QUICK_NEEDS_SOURCE: {
      title: 'İndirilecek bir şey belirtilmedi',
      body: 'Tek tıkla indirmek için bir video bağlantısı ya da incelenmiş bir video gerekir.',
    },
    QUICK_NEEDS_VIDEO: {
      title: 'Bu bir oynatma listesi',
      body: 'Tek tıkla indirme tek bir video içindir. Listeyi uygulamada incele ve videoyu oradan seç.',
    },
    AUDIO_LANGUAGE_UNKNOWN: {
      title: 'Bu dilde ses yok',
      body: 'Seçtiğin dilde bir ses parçası bu videoda bulunmuyor. Videonun sunduğu dillerden birini seç.',
    },
    QUICK_NOTHING_OFFERED: {
      title: 'Bu videoda indirilebilir bir kalite yok',
      body: 'Site hiçbir indirilebilir görüntü ya da ses sunmuyor; içerik DRM korumalı olabilir.',
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
      body: 'Ev klasörünün kendisi, Kitaplık ya da bir sistem klasörü seçilemez. Filmler veya Belgeler altında bir klasör seç.',
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
    SOURCE_NOT_FOUND: { title: 'Dosya bulunamadı', body: 'Yolu kontrol et; tam yol (/ ile başlayan) olmalı.' },
    SOURCE_NOT_MEDIA: {
      title: 'Bu bir medya dosyası değil',
      body: 'FFmpeg bu dosyada görüntü, ses ya da altyazı bulamadı.',
    },
    OUTPUT_DIR_NOT_ALLOWED: {
      title: 'Bu klasöre yazılamaz',
      body: 'Stüdyo çıktıları kaynağın yanına ya da indirme klasörüne yazılır.',
    },
    SUBTITLE_EMPTY: { title: 'Altyazı boş kaldı', body: 'Kaydırma bütün satırları sıfırın öncesine itti.' },
    OUTPUT_EMPTY: {
      title: 'FFmpeg boş bir dosya üretti',
      body: 'Seçilen aralıkta kopyalanabilecek veri yok. Aralığı genişlet ya da “Kare hassas”ı dene.',
    },
    LOUDNESS_SILENT: { title: 'Ses tamamen sessiz', body: 'Sessiz bir kaydın seviyesi eşitlenemez.' },
    INVALID_OPTION: { title: 'Geçersiz değer', body: 'Alanlardan biri sayı bekliyor.' },
    UNKNOWN_OPERATION: { title: 'Bilinmeyen işlem', body: 'Sayfayı yenileyip tekrar dene.' },
    UNKNOWN_CONTAINER: { title: 'Bilinmeyen kap', body: 'MKV, MP4 veya MOV seç.' },
    UNKNOWN_SUBTITLE_FORMAT: { title: 'Bilinmeyen altyazı biçimi', body: 'SRT, VTT veya ASS seç.' },
    UNKNOWN_SUBTITLE_ACTION: { title: 'Bilinmeyen altyazı işlemi', body: 'Sayfayı yenileyip tekrar dene.' },
    UNKNOWN_AUDIO_CODEC: { title: 'Bilinmeyen ses biçimi', body: 'Listeden bir biçim seç.' },
    LOUDNESS_MEASURE_FAILED: {
      title: 'Ses seviyesi ölçülemedi',
      body: 'Ham kayda bak. Eşitlemeyi kapatıp tekrar dene.',
    },
    ITEM_NOT_TRASHABLE: {
      title: 'Bu öğe çöpe atılamaz',
      body: 'Zaten çöpte ya da dosyası eksik. Önce “Dosyaları denetle”yi dene.',
    },
    TRASH_FAILED: { title: 'Çöp Kutusu’na taşınamadı', body: 'Dosya kilitli ya da erişim izni yok.' },
    SCAN_BUSY: { title: 'Denetim zaten sürüyor', body: 'Bitmesini bekle.' },
    JOBS_RUNNING: {
      title: 'Önce indirmelerin bitmesini bekle',
      body: 'yt-dlp, çalışan bir indirmenin altından değiştirilemez.',
    },
    DOWNLOAD_DIR_NOT_A_FOLDER: { title: 'Bu bir klasör değil', body: 'Bir klasör seç.' },
    DOWNLOAD_DIR_MISSING: {
      title: 'Klasör bulunamadı',
      body: 'Üst klasör yok. Var olan bir klasör seç.',
    },
    DOWNLOAD_DIR_NOT_WRITABLE: {
      title: 'Bu klasöre yazılamıyor',
      body: 'Yazma iznin olan bir klasör seç.',
    },
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
    USED_SAFARI_LOGIN: 'Bu video giriş istediği için Safari’deki YouTube oturumunla açıldı; indirmesi de oturumla yapılır.',
    DRM_PRESENT: 'Bu videonun bazı formatları DRM korumalı ve indirilemez.',
    DRM_MAYBE: 'Bazı formatlar DRM korumalı olabilir; indirme sırasında başarısız olabilirler.',
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
