## Restart the worker pool
Drain the queue, then restart workers one at a time so in-flight jobs finish.
A full pool restart is the documented fix for a saturated work queue.

## Rollback
Re-deploy the previous image tag. Rollback does not revert database migrations.

## Scaling the pool
Add workers when queue depth stays above two hundred for five minutes.
Scaling out does not clear an existing lock; restart the pool for that.

## On-call handover
The outgoing engineer writes a handover note listing open incidents.

## Log locations
Worker logs are under /var/log/cobalt/worker. Retention is fourteen days.
