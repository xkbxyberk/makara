import { describe, expect, it } from 'vitest';
import {
  formatBitrate,
  formatBytes,
  formatDuration,
  formatUploadDate,
  languageName,
  sizePrefix,
} from './format';

describe('formatBytes', () => {
  it('uses binary units and drops decimals when they add nothing', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(999)).toBe('999 B');
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(905889370)).toBe('864 MB');
  });
  it('renders an em dash for missing values rather than 0', () => {
    expect(formatBytes(null)).toBe('–');
    expect(formatBytes(undefined)).toBe('–');
  });
});

describe('sizePrefix', () => {
  it('marks how much a size can be trusted', () => {
    expect(sizePrefix('exact')).toBe('');
    expect(sizePrefix('approx')).toBe('≈');
    expect(sizePrefix('estimated')).toBe('~');
    expect(sizePrefix('partial')).toBe('≥');
  });
});

describe('formatDuration', () => {
  it('only shows hours when there are hours', () => {
    expect(formatDuration(59)).toBe('0:59');
    expect(formatDuration(605)).toBe('10:05');
    expect(formatDuration(1541)).toBe('25:41');
    expect(formatDuration(3661)).toBe('1:01:01');
    expect(formatDuration(null)).toBe('–');
  });
});

describe('formatBitrate', () => {
  it('switches to Mbps past 1000 kbps', () => {
    expect(formatBitrate(128)).toBe('128 kbps');
    expect(formatBitrate(4500)).toBe('4.5 Mbps');
    expect(formatBitrate(null)).toBe('–');
  });
});

describe('formatUploadDate', () => {
  it('accepts yt-dlp YYYYMMDD and rejects anything else', () => {
    expect(formatUploadDate('20211124')).toContain('2021');
    expect(formatUploadDate('nope')).toBe('–');
  });
});

describe('languageName', () => {
  it('translates codes and strips the audio-description suffix', () => {
    expect(languageName('tr')).toBe('Türkçe');
    expect(languageName('en-desc')).toBe(languageName('en'));
    expect(languageName(null)).toBe('bilinmiyor');
  });
});
