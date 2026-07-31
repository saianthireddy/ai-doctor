## Summary
On 14 March the work queue saturated for forty minutes and jobs timed out.

## Impact
Roughly eight percent of scheduled jobs failed. No data was lost.

## Root cause
A slow downstream dependency held locks far longer than expected, so the queue
filled and workers reported timeouts.

## Resolution
The worker pool was restarted and the dependency timeout was lowered.

## Follow-up actions
Alert on queue depth, not only on error rate.
