import { useEffect, useRef, useState } from 'react';
import type { Job } from './api';

export type Connection = 'connecting' | 'open' | 'reconnecting';

/**
 * The live job list over Server-Sent Events. The server sends a full snapshot on connect and
 * then one event per change; EventSource reconnects by itself, and each reconnect brings a
 * fresh snapshot, so nothing is ever missed or double-applied.
 */
export function useJobs(onTransition?: (job: Job, previous: Job | undefined) => void) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [connection, setConnection] = useState<Connection>('connecting');
  const known = useRef(new Map<string, Job>());
  const transition = useRef(onTransition);
  transition.current = onTransition;

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
      if (previous?.status !== job.status) transition.current?.(job, previous);
      publish();
    });
    source.addEventListener('removed', (event) => {
      const { id } = JSON.parse((event as MessageEvent<string>).data) as { id: string };
      known.current.delete(id);
      publish();
    });
    return () => source.close();
  }, []);

  return { jobs, connection };
}

export const isActive = (job: Job) => job.status === 'queued' || job.status === 'running';
