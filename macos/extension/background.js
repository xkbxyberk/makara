// N0 spike: prove the extension -> native handler -> local backend round trip.
// The native side answers every message; nothing here touches the page you are on.

async function ping(reason) {
  try {
    const reply = await browser.runtime.sendNativeMessage('application.id', { type: 'ping', reason });
    await browser.storage.local.set({ lastPing: { at: Date.now(), reason, reply } });
    // Echo what came back, so the native log shows the whole round trip.
    await browser.runtime.sendNativeMessage('application.id', { type: 'report', reason, reply });
  } catch (error) {
    await browser.storage.local.set({ lastPing: { at: Date.now(), reason, error: String(error) } });
  }
}

browser.runtime.onStartup.addListener(() => void ping('startup'));
browser.runtime.onInstalled.addListener(() => void ping('installed'));
browser.runtime.onMessage.addListener((message) => {
  if (message?.type === 'ping') return ping('popup').then(() => browser.storage.local.get('lastPing'));
  return undefined;
});
