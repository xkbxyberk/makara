import { SettingsRoute } from './routes/SettingsRoute';

/** What the native app's Settings window (⌘,) shows: the settings screen alone. The window
 * follows the system appearance, so there is no theme to set here. */
export function SettingsWindow() {
  return (
    <div className="content settings-window">
      <SettingsRoute theme="system" setTheme={() => undefined} onSaved={() => undefined} />
    </div>
  );
}
