// The toolbar popup: inspect the page, show the choices this video really has (the backend's
// `offers`), download with one click. Every text node is set with textContent, never as HTML:
// titles and channel names come from the site.
const t = (key, ...subs) => browser.i18n.getMessage(key, subs.map(String));
const app = document.getElementById('app');

const MODES = [
  ['mkv', 'mode_mkv'],
  ['compat_mp4', 'mode_mp4'],
  ['audio', 'mode_audio'],
];
// The backend's roles (normalize.audio_role). It cannot tell a human dub from an AI one, and
// says so; an unknown role is just "Ses", never guessed to be a dub.
const ROLE_KEYS = { original: 'role_original', default: 'role_default', dub: 'role_dub', descriptive: 'role_description', unknown: 'role_unknown' };

const state = {
  tab: null,
  // What to download: the post the page's player belongs to (found by content.js), else the page.
  url: null,
  // Whether the app offers downloads on the page (Ayarlar), and whether this site is muted.
  offerMode: null,
  muted: false,
  rule: null,
  model: null,
  mode: 'mkv',
  offerId: null,
  // The row Berk clicked. Only if it is still the chosen one when he downloads does it become the
  // remembered choice: a preselected match, or a default after switching output, never does
  // (that ratchets a whole site down to whatever one video happened to offer).
  pickedId: null,
  busy: false,
  language: null, // null: the original audio
  subtitles: 'default', // 'default' | 'none' | a subtitle key
};

/** A tiny element builder: attributes, then children (strings become text, never HTML). */
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (name.startsWith('on')) el.addEventListener(name.slice(2), value);
    else if (name === 'class') el.className = value;
    else el.setAttribute(name, value === true ? '' : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function show(...nodes) {
  app.replaceChildren(...nodes, offerSwitch());
}

/** "Suggest downloads on this site": undoes the card's "Bu sitede sorma". */
function offerSwitch() {
  if (state.offerMode !== 'page' || !VD.siteOf(state.url ?? '')) return '';
  const box = h('input', {
    type: 'checkbox',
    checked: !state.muted,
    onchange: async (event) => {
      state.muted = !event.target.checked;
      const stored = (await browser.storage.local.get('offerMuted'))?.offerMuted ?? {};
      const site = VD.siteOf(state.url);
      if (state.muted) stored[site] = true;
      else delete stored[site];
      await browser.storage.local.set({ offerMuted: stored });
    },
  });
  return h('label', { class: 'offer-switch' }, box, t('popup_offer_here', VD.siteOf(state.url)));
}

async function loadOfferState() {
  const reply = await VD.api('api/extension');
  state.offerMode = reply.ok ? reply.json?.offer : null;
  const stored = (await browser.storage.local.get('offerMuted').catch(() => ({})))?.offerMuted ?? {};
  state.muted = stored[VD.siteOf(state.url ?? '')] === true;
}

async function targetOf(tab) {
  const key = `target:${tab.id}`;
  const stored = await browser.storage.session?.get(key).catch(() => ({}));
  const target = stored?.[key];
  return target && VD.isWebPage(target.url) && target.kind !== 'playlist' ? target.url : tab.url;
}

function message(title, body, ...actions) {
  show(
    h('p', { class: 'message' }, title ? h('strong', {}, title) : null, body),
    actions.length ? h('div', { class: 'actions' }, ...actions) : null,
  );
}

function errorText(code, status) {
  const text = code ? browser.i18n.getMessage(`error_${code}`) : '';
  if (text) return text;
  return code ? t('error_generic', code) : t('error_http', status ?? '?');
}

function languageName(code) {
  try {
    return new Intl.DisplayNames(['tr'], { type: 'language' }).of(code) ?? code;
  } catch {
    return code;
  }
}

function openInApp() {
  void VD.openApp(VD.inspectLink(state.url)).then(() => window.close());
}

const openInAppButton = () => h('button', { class: 'btn', type: 'button', onclick: openInApp }, t('popup_open_in_app'));

// ---- flow -------------------------------------------------------------------------------------

async function main() {
  // Tells the background the menu is up (it may have opened it itself, for a playing video).
  void browser.runtime.sendMessage({ type: 'popup-open' }).catch(() => undefined);
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  state.tab = tab ?? null;
  if (!tab || !VD.isWebPage(tab.url)) {
    message(null, t('popup_not_a_page'));
    return;
  }
  state.url = await targetOf(tab);
  if (!(await appIsUp())) return;
  await loadOfferState();
  state.rule = await VD.loadRule(state.url);
  await inspect();
}

async function appIsUp() {
  if ((await VD.api('api/health')).ok) return true;
  message(
    t('popup_offline_title'),
    t('popup_offline_body'),
    h('button', { class: 'btn primary', type: 'button', onclick: startApp }, t('popup_open_app')),
  );
  return false;
}

async function startApp() {
  show(h('p', { class: 'message' }, h('span', { class: 'spinner' }), t('popup_starting')));
  await VD.openApp();
  for (let i = 0; i < 60; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    if ((await VD.api('api/health')).ok) {
      await loadOfferState();
      state.rule = await VD.loadRule(state.url);
      await inspect();
      return;
    }
  }
  await appIsUp();
}

async function inspect() {
  show(
    h('h1', {}, state.tab.title || state.tab.url),
    h('p', { class: 'message' }, h('span', { class: 'spinner' }), t('popup_inspecting')),
  );
  // `reuse`: reopening the popup on the same page is instant (the app keeps recent inspections).
  const reply = await VD.api('api/inspect', { method: 'POST', body: { url: state.url, reuse: true, rule: state.rule } });
  if (reply.offline) {
    await appIsUp();
    return;
  }
  if (!reply.ok) {
    message(null, errorText(reply.json?.error?.code, reply.status), openInAppButton());
    return;
  }
  const model = reply.json;
  state.model = model;
  if (model.kind === 'playlist') {
    message(t('popup_playlist_title'), t('popup_playlist_body'), openInAppButton());
    return;
  }
  const offers = model.offers ?? { video: [], audio: [] };
  if (!offers.video.length && !offers.audio.length) {
    const drm = (model.warnings ?? []).includes('DRM_PRESENT');
    message(null, drm ? t('popup_drm') : t('popup_nothing'), openInAppButton());
    return;
  }
  const pre = offers.preselected;
  const preRow = [...offers.video, ...offers.audio].find((row) => row.id === pre?.offer_id);
  state.mode = preRow?.kind === 'audio' ? 'audio' : (pre?.output ?? 'mkv');
  state.offerId = preRow?.id ?? null;
  renderChoices();
}

// ---- choices ----------------------------------------------------------------------------------

function rowsFor(mode) {
  const offers = state.model.offers;
  return mode === 'audio' ? offers.audio : offers.video;
}

/** Switching output keeps the chosen size if it exists there, else today's default for it. */
function defaultRowFor(mode) {
  const rows = rowsFor(mode);
  const current = rows.find((row) => row.id === state.offerId);
  if (current) return current.id;
  if (mode === 'audio') return (rows.find((row) => row.format === 'mp3') ?? rows[0])?.id ?? null;
  return (rows.find((row) => row.outputs[mode]?.recommended) ?? rows[0])?.id ?? null;
}

function sizeCell(size, step) {
  if (!size?.bytes) {
    return h('span', { class: 'size muted' }, step === 'transcode' ? t('size_later') : t('size_unknown'));
  }
  return h('span', { class: 'size' }, `${VD.sizePrefix(size.kind)}${VD.formatBytes(size.bytes)}`);
}

function stepBadge(step) {
  if (step === 'transcode') return h('span', { class: 'badge warn' }, t('step_transcode'));
  if (step === 'probe') return h('span', { class: 'badge' }, t('step_probe'));
  return null;
}

function rowView(row) {
  const checked = row.id === state.offerId;
  const rule = state.rule;
  // Said only where the remembered choice itself is on offer, not of the nearest stand-in.
  const remembered = rule && (row.kind === 'video'
    ? rule.kind === 'video' && row.height === rule.height && (rule.output ?? 'mkv') === state.mode
    : rule.kind === 'audio' && row.format === rule.format);
  let label;
  let detail;
  let size;
  let badges;
  if (row.kind === 'video') {
    const out = row.outputs[state.mode];
    label = row.height ? `${row.height}p` : '—';
    detail = [out.vcodec_label, row.fps ? t('fps', row.fps) : null].filter(Boolean).join(' · ');
    size = sizeCell(out.size, out.step);
    badges = [
      row.dynamic_range && row.dynamic_range !== 'SDR' ? h('span', { class: 'badge' }, row.dynamic_range) : null,
      row.ai_upscaled ? h('span', { class: 'badge warn' }, t('badge_ai')) : null,
      stepBadge(out.step),
    ];
  } else {
    label = t(`format_${row.format}`);
    detail = [row.source_codec_label, row.abr ? `${Math.round(row.abr)} kbps` : null].filter(Boolean).join(' · ');
    size = sizeCell(row.size, row.step);
    badges = [row.step === 'copy' ? h('span', { class: 'badge ok' }, t('step_copy')) : stepBadge(row.step)];
  }
  return h(
    'button',
    {
      class: 'row',
      type: 'button',
      role: 'radio',
      'aria-checked': checked ? 'true' : 'false',
      'data-offer-id': row.id,
      onclick: () => {
        state.offerId = row.id;
        state.pickedId = row.id;
        renderChoices();
      },
    },
    h('span', { class: 'dot' }),
    h('span', { class: 'label' }, label),
    h('span', { class: 'detail' }, detail, ...badges, remembered ? h('span', { class: 'remembered' }, t('remembered')) : null),
    size,
  );
}

function languageField() {
  // The first group is the original (the default); others can only be asked for by language.
  const groups = (state.model.audio_languages ?? []).filter((group, index) => index === 0 || group.language);
  if (groups.length < 2) return [];
  const select = h(
    'select',
    {
      'aria-label': t('label_audio'),
      onchange: (event) => {
        state.language = event.target.value || null;
      },
    },
    ...groups.map((group, index) =>
      h(
        'option',
        { value: index === 0 ? '' : group.language, selected: (state.language ?? '') === (index === 0 ? '' : group.language) },
        `${group.language ? languageName(group.language) : t('role_unknown')} (${t(ROLE_KEYS[group.role] ?? 'role_unknown')})`,
      ),
    ),
  );
  return [h('span', {}, t('label_audio')), select];
}

function subtitleField() {
  if (state.mode === 'audio') return [];
  const manual = state.model.subtitles?.manual ?? [];
  const defaults = state.model.defaults?.mkv?.subtitle_keys ?? [];
  const select = h(
    'select',
    {
      'aria-label': t('label_subtitles'),
      onchange: (event) => {
        state.subtitles = event.target.value;
      },
    },
    h('option', { value: 'default', selected: state.subtitles === 'default' },
      defaults.length ? t('subs_default', defaults.map(languageName).join(', ')) : t('subs_default_none')),
    h('option', { value: 'none', selected: state.subtitles === 'none' }, t('subs_none')),
    ...manual.map((sub) => h('option', { value: sub.key, selected: state.subtitles === sub.key }, languageName(sub.language))),
  );
  return [h('span', {}, t('label_subtitles')), select];
}

function renderChoices() {
  const { model } = state;
  if (!rowsFor(state.mode).some((row) => row.id === state.offerId)) state.offerId = defaultRowFor(state.mode);
  const media = model.media ?? {};
  const fields = [...languageField(), ...subtitleField()];
  show(
    h('header', {}, h('h1', {}, media.title ?? state.tab.title),
      h('div', { class: 'meta' }, [media.channel ?? media.uploader, VD.formatDuration(media.duration)].filter(Boolean).join(' · '))),
    h(
      'div',
      { class: 'segmented', role: 'radiogroup' },
      ...MODES.filter(([value]) => rowsFor(value).length > 0).map(([value, key]) =>
        h('button', {
          class: 'segment', type: 'button', role: 'radio', 'aria-checked': state.mode === value ? 'true' : 'false',
          onclick: () => {
            state.mode = value;
            state.offerId = defaultRowFor(value);
            renderChoices();
          },
        }, t(key)),
      ),
    ),
    h('div', { class: 'rows', role: 'radiogroup' }, ...rowsFor(state.mode).map(rowView)),
    fields.length ? h('div', { class: 'fields' }, ...fields) : null,
    h('div', { class: 'actions' },
      h('button', { class: 'link', type: 'button', onclick: openInApp }, t('popup_open_in_app')),
      h('button', { class: 'btn primary', type: 'button', onclick: download, disabled: !state.offerId }, t('download'))),
  );
}

// ---- downloading ------------------------------------------------------------------------------

async function download() {
  if (state.busy) return; // a double click must not queue it twice
  state.busy = true;
  for (const button of app.querySelectorAll('button')) button.disabled = true;
  const body = {
    inspect_id: state.model.inspect_id,
    offer_id: state.offerId,
    output: state.mode === 'audio' ? null : state.mode,
    audio_language: state.language,
  };
  if (state.mode !== 'audio' && state.subtitles !== 'default') {
    body.subtitle_keys = state.subtitles === 'none' ? [] : [state.subtitles];
  }
  let reply = await VD.api('api/quick', { method: 'POST', body });
  if (reply.status === 410) {
    // The app restarted since the inspect: inspect again, then the same choice.
    const fresh = await VD.api('api/inspect', { method: 'POST', body: { url: state.url, reuse: false } });
    if (fresh.ok) {
      state.model = fresh.json;
      reply = await VD.api('api/quick', { method: 'POST', body: { ...body, inspect_id: fresh.json.inspect_id } });
    }
  }
  state.busy = false;
  if (reply.offline) {
    await appIsUp();
    return;
  }
  if (!reply.ok) {
    message(null, errorText(reply.json?.error?.code, reply.status), openInAppButton());
    return;
  }
  if (state.pickedId && state.pickedId === state.offerId) await VD.saveRule(state.url, reply.json.rule);
  await follow(reply.json.job.id);
}

async function follow(jobId) {
  const title = state.model.media?.title ?? state.tab.title;
  const bar = h('div');
  const status = h('p', { class: 'message' }, t('queued'));
  const sessionNote = h('p', { class: 'message', hidden: true }, t('used_session'));
  const showDownloads = h('button', {
    class: 'btn', type: 'button',
    onclick: () => void VD.openApp('videodownloader://show?route=download').then(() => window.close()),
  }, t('show_downloads'));
  show(h('h1', {}, title), h('div', { class: 'progress' }, bar), status, sessionNote, h('div', { class: 'actions' }, showDownloads));
  // Give up after a while without news (the app quit, or the job was removed there).
  for (let misses = 0; misses < 10; ) {
    const reply = await VD.api('api/jobs');
    const job = reply.ok ? reply.json.find((j) => j.id === jobId) : null;
    misses = job ? 0 : misses + 1;
    if (job) {
      sessionNote.hidden = !job.used_session;
      const stage = browser.i18n.getMessage(`stage_${job.status === 'running' ? job.stage : job.status}`) || job.stage;
      bar.style.width = `${Math.round((job.progress ?? 0) * 100)}%`;
      if (job.status === 'done') {
        status.textContent = t('stage_done');
        bar.style.width = '100%';
        return;
      }
      if (job.status === 'failed' || job.status === 'cancelled') {
        status.textContent = job.status === 'failed' ? errorText(job.error_code) : t('stage_cancelled');
        status.classList.add('error');
        return;
      }
      status.textContent = job.status === 'running' ? t('progress', stage, Math.round((job.progress ?? 0) * 100)) : stage;
    }
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
  status.textContent = t('job_gone');
}

void main();
