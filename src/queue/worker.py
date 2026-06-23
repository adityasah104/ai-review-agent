import asyncio
import threading
import time
import structlog
from sqlalchemy.orm import Session
from src.db.database import SessionLocal
from src.db.models import ReviewJob
from src.agents.graph import graph
from src.agents.state import PRReviewState

log = structlog.get_logger()

POLL_INTERVAL_SECONDS = 3


def _get_next_pending_job(db: Session):
    """Returns the oldest PENDING job and marks it PROCESSING atomically."""
    job = (
        db.query(ReviewJob)
        .filter(ReviewJob.status == "PENDING")
        .order_by(ReviewJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if job:
        job.status = "PROCESSING"
        db.commit()
        db.refresh(job)
    return job


async def _process_job(job: ReviewJob):
    """Runs the full LangGraph review pipeline for a single job."""
    log.info("job_processing_start", job_id=job.id, pr_id=job.pr_id)

    initial_state = PRReviewState(
        job_id=job.id,
        pr_id=job.pr_id,
        repository_id=job.repository_id,
        project=job.project,
        source_branch=job.source_branch,
        target_branch=job.target_branch,
        pr_url=job.pr_url or "",
        pr_title=job.pr_title or "",
        ci_fix_attempts=job.ci_fix_attempts,
    )

    db = SessionLocal()
    try:
        final_state = await graph.ainvoke(initial_state)

        job_record = db.query(ReviewJob).filter(ReviewJob.id == job.id).first()
        if job_record:
            job_record.status = "DONE"
            job_record.result_summary = final_state.get("review_summary", "")
            job_record.ci_fix_attempts = final_state.get("ci_fix_attempts", 0)
            db.commit()

        log.info("job_processing_done", job_id=job.id)

    except Exception as e:
        log.error("job_processing_failed", job_id=job.id, error=str(e))
        job_record = db.query(ReviewJob).filter(ReviewJob.id == job.id).first()
        if job_record:
            job_record.status = "FAILED"
            job_record.error_message = str(e)
            db.commit()
    finally:
        db.close()


def _worker_loop():
    """
    Background thread: polls SQLite every 3 seconds for PENDING jobs.
    Processes one job at a time (sequential, no concurrency issues).
    """
    log.info("worker_thread_started")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        db = SessionLocal()
        try:
            job = _get_next_pending_job(db)
            if job:
                log.info("worker_picked_job", job_id=job.id)
                loop.run_until_complete(_process_job(job))
            else:
                time.sleep(POLL_INTERVAL_SECONDS)
        except Exception as e:
            log.error("worker_loop_error", error=str(e))
            time.sleep(POLL_INTERVAL_SECONDS)
        finally:
            db.close()


def start_worker_thread():
    """Starts the background worker thread. Call once on app startup."""
    thread = threading.Thread(target=_worker_loop, daemon=True, name="review-worker")
    thread.start()
    log.info("worker_thread_launched")
    return thread