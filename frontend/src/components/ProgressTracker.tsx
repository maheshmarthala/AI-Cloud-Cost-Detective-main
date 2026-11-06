import type { ProgressEvent } from '../types';
export default function ProgressTracker({ events }: {events: ProgressEvent[]}) {
  return <section className="card" aria-live="polite"><h2>Investigation progress</h2><ol className="progress">{events.map((event, index)=><li key={index} className={event.status === 'failed' ? 'error' : ''}><span>{event.status === 'failed' ? '!' : '✓'}</span>{event.message}</li>)}</ol></section>;
}
