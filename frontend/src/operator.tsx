import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import OperatorSurface from './components/OperatorSurface';
import './index.css';

/**
 * Entry point for the OPERATOR surface — deliberately separate from `main.tsx`.
 *
 * This is the mechanism behind §8's "must survive model/runtime failure". Two HTML
 * entries means two independent bundles with no shared chunk: if the analyst console's
 * stream, charting or model plumbing is what is broken, nothing here imports it and
 * nothing here can be taken down with it. Verified by
 * `scripts/verify_operator_isolation.py`, which fails if any analyst-only module name
 * appears in the operator bundle.
 *
 * Deliberately minimal. It does not open the SSE stream, does not subscribe to
 * anything, and renders entirely from static data on first paint — a page that
 * required a live connection to tell an operator what the system can do would be no use
 * during the incident it exists for.
 */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <OperatorSurface />
  </StrictMode>,
);
