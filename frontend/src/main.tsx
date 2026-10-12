import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { SettingsWindow } from './SettingsWindow';
import { settingsWindow } from './lib/embedded';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {settingsWindow ? <SettingsWindow /> : <App />}
  </StrictMode>,
);
