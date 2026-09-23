import { useState } from 'react';
import { tr } from '../i18n/tr';
import { ApiError, api, type Job } from '../lib/api';
import { formatBytes, formatDuration } from '../lib/format';
import type { Connection } from '../lib/jobs';
import { Badge, EmptyState, LoadingState, Notice, Panel } from '../components/ui';

const INDETERMINATE = new Set(['starting', 'preparing', 'postprocessing', 'cancelling']);

function JobError({ job }: { job: Job }) {
  const [open, setOpen] = useState(false);
  const table = tr.errors as Record<string, { title: string; body: string }>;
  const copy = table[job.error_code ?? 'UNKNOWN'] ?? tr.errors.UNKNOWN;
  return (
    <div className="job-error" role="alert">
      <strong>{copy.title}</strong> <span className="muted">{copy.body}</span>
      {job.error_raw && (
        <>
          {' '}
          <button type="button" className="btn btn-quiet" onClick={() => setOpen((v) => !v)}>
            {open ? tr.app.hideDetails : tr.app.showDetails}
          </button>
          {open && <pre className="mono muted raw-log">{job.error_raw}</pre>}
        </>
      )}
    </div>
  );
}

function ProgressBar({ job }: { job: Job }) {
  const indeterminate = job.status === 'running' && (INDETERMINATE.has(job.stage) || job.progress <= 0);
  const percent = Math.round(job.progress * 100);
  return (
    <div
      className={indeterminate ? 'progress indeterminate' : 'progress'}
      role="progressbar"
      aria-label={tr.queue.stages[job.stage] ?? job.stage}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : percent}
    >
      <div className="progress-fill" style={{ width: indeterminate ? undefined : `${percent}%` }} />
    </div>
  );
}

function JobRow({ job }: { job: Job }) {
  const [failure, setFailure] = useState<string | null>(null);
  const act = (action: () => Promise<unknown>) => () => {
    setFailure(null);
    action().catch((error: unknown) => setFailure(error instanceof ApiError ? error.code : 'UNKNOWN'));
  };
  const tone = { done: 'ok', failed: 'danger', cancelled: 'neutral', running: 'accent', queued: 'neutral' } as const;
  const live = job.status === 'running';
  return (
    <li className="job" data-testid="job" data-status={job.status}>
      <div className="job-head">
        <strong className="job-title">{job.title ?? job.source_url}</strong>
        <Badge>{tr.download.modes[job.mode]}</Badge>
        <Badge tone={tone[job.status]}>{tr.queue.statuses[job.status]}</Badge>
        <div className="job-actions">
          {(job.status === 'queued' || job.status === 'running') && (
            <button type="button" className="btn" onClick={act(() => api.cancel(job.id))}>
              {tr.queue.cancel}
            </button>
          )}
          {(job.status === 'failed' || job.status === 'cancelled') && (
            <button type="button" className="btn" onClick={act(() => api.retry(job.id))}>
              {tr.queue.retry}
            </button>
          )}
          {job.status !== 'running' && (
            <button
              type="button"
              className="btn btn-quiet"
              title={tr.queue.removeHelp}
              onClick={act(() => api.remove(job.id))}
            >
              {tr.queue.remove}
            </button>
          )}
        </div>
      </div>
      {(live || job.status === 'queued') && (
        <>
          <ProgressBar job={job} />
          <div className="job-meta muted">
            <span>{tr.queue.stages[job.stage] ?? job.stage}</span>
            {live && job.progress > 0 && <span>{Math.round(job.progress * 100)}%</span>}
            {live && job.item_index && job.item_count && job.item_count > 1 && (
              <span>{tr.queue.item(job.item_index, job.item_count)}</span>
            )}
            {live && job.speed ? <span>{tr.queue.speed(formatBytes(job.speed))}</span> : null}
            {live && job.eta ? <span>{tr.queue.eta(formatDuration(job.eta))}</span> : null}
          </div>
        </>
      )}
      {job.status === 'failed' && <JobError job={job} />}
      {job.status === 'done' && job.output_files.length > 0 && (
        <ul className="job-files">
          {job.output_files.map((file) => (
            <li key={file}>
              <span className="mono path">{file.split('/').slice(-2).join('/')}</span>
              <button type="button" className="btn btn-quiet" onClick={act(() => api.reveal(file))}>
                {tr.queue.reveal}
              </button>
            </li>
          ))}
        </ul>
      )}
      {failure && (
        <Notice tone="danger">
          {(tr.errors as Record<string, { title: string }>)[failure]?.title ?? failure}
        </Notice>
      )}
    </li>
  );
}

export function QueueRoute({ jobs, connection }: { jobs: Job[] | null; connection: Connection }) {
  return (
    <div className="content-inner">
      {connection === 'reconnecting' && <Notice tone="warn">{tr.queue.reconnecting}</Notice>}
      <Panel title={tr.queue.title} count={jobs?.length} flush>
        {jobs === null ? (
          <LoadingState title={tr.queue.loading} body="" />
        ) : jobs.length === 0 ? (
          <EmptyState glyph="↓" title={tr.queue.emptyTitle} body={tr.queue.emptyBody} />
        ) : (
          <ul className="jobs">
            {jobs.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
