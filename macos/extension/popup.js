const status = document.getElementById('status');
const t = (key) => browser.i18n.getMessage(key);

status.textContent = t('popup_checking');
const result = await browser.runtime.sendMessage({ type: 'ping' });
const reply = result?.lastPing?.reply;
status.textContent = reply?.ok ? t('popup_connected') : t('popup_unreachable');
