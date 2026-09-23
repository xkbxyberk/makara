import { useEffect, useRef, useState } from 'react';
import type { Job } from './api';

export type Connection = 'connecting' | 'open' | 'reconnecting';

/**
 * The live job list over Server-Sent Events. The server sends a full snapshot on connect and
 * then one event per change; EventSource reconnects by itself, and each reconnect brings a
 * fresh snapshot, so nothing is ever missed or double-applied.
 */
export interface ServerEventHandlers {
  onTransition?: (job: Job, previous: Job | undefined) => void;
  /** The opt-in clipboard watcher saw a link being copied. */
  onClipboard?: (url: string) => void;
  /** A finished download was added to the library. */
  onLibrary?: () => void;
  /** A finished download could not be catalogued (its file is still on disk). */
  onLibraryError?: () => void;
}

export function useJobs(handlers: ServerEventHandlers = {}) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [connection, setConnection] = useState<Connection>('connecting');
  const known = useRef(new Map<string, Job>());
  const latest = useRef(handlers);
  latest.current = handlers;

  useEffect(() => {
    const source = new EventSource('/api/events');
    const publish = () =>
      setJobs([...known.current.values()].sort((a, b) => b.created_at - a.created_at));

    source.addEventListener('open', () => setConnection('open'));
    source.addEventListener('error', () => setConnection('reconnecting'));
    source.addEventListener('snapshot', (event) => {
      const list = JSON.parse((event as MessageEvent<string>).data) as Job[];
      known.current = new Map(list.map((job) => [job.id, job]));
      setConnection('open');
      publish();
    });
    source.addEventListener('job', (event) => {
      const { job } = JSON.parse((event as MessageEvent<string>).data) as { job: Job };
      const previous = known.current.get(job.id);
      known.current.set(job.id, job);
      if (previous?.status !== job.status) latest.current.onTransition?.(job, previous);
      publish();
    });
    source.addEventListener('removed', (event) => {
      const { id } = JSON.parse((event as MessageEvent<string>).data) as { id: string };
      known.current.delete(id);
      publish();
    });
    source.addEventListener('clipboard', (event) => {
      const { url } = JSON.parse((event as MessageEvent<string>).data) as { url: string };
      latest.current.onClipboard?.(url);
    });
    source.addEventListener('library', () => latest.current.onLibrary?.());
    source.addEventListener('library_error', () => latest.current.onLibraryError?.());
    return () => source.close();
  }, []);

  return { jobs, connection };
}

export const isActive = (job: Job) => job.status === 'queued' || job.status === 'running';
