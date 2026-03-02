"""
PostgreSQL-backed Jobs Worker Implementation.

This worker processes jobs from Redis queues and persists results to PostgreSQL.
It implements the full job lifecycle: queued → running → finished/failed.

Features:
- Consumes jobs from Redis queues by tenant
- Executes job logic based on job type
- Updates PostgreSQL with status transitions
- Handles cancellation via Redis cancel flags
- Implements heartbeat mechanism
- Logs events to PostgreSQL job_events table
- Supports agent.run jobs with full orchestrator integration

Usage:
    python -m src.workers.jobs_worker

Environment Variables:
    USE_POSTGRES_JOBS: Enable PostgreSQL backend (default: false)
    JOB_WORKER_POLL_INTERVAL: Queue polling interval in seconds (default: 1.0)
    JOB_WORKER_HEARTBEAT_INTERVAL: Status update interval in seconds (default: 5.0)
    DATABASE_URL: PostgreSQL connection string
    REDIS_URL: Redis connection string
"""

import asyncio
import contextlib
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

# Core dependencies
from sqlalchemy.orm import Session

# Database connections
from db.postgres_control.database import get_db
from db.redis_cache import jobs_cache
from src.config import settings

# Services and models
from src.services.jobs_service import JobsService

# PII scrubbing (optional but recommended)
try:
    from src.security.pii_scrubber import scrub_dict as pii_scrub_dict
    PII_SCRUBBER_AVAILABLE = True
except ImportError:
    PII_SCRUBBER_AVAILABLE = False
    pii_scrub_dict = None  # type: ignore

# Output guard (optional)
try:
    from src.security.output_guard import guard_text, OutputGuardResult
    OUTPUT_GUARD_AVAILABLE = True
except ImportError:
    OUTPUT_GUARD_AVAILABLE = False
    guard_text = None  # type: ignore

# Agent metrics (optional)
try:
    from src.metrics import agent_metrics
    AGENT_METRICS_AVAILABLE = True
except ImportError:
    AGENT_METRICS_AVAILABLE = False
    agent_metrics = None  # type: ignore

logger = logging.getLogger(__name__)


class JobsWorker:
    """
    Background worker for processing jobs with PostgreSQL persistence.

    Architecture:
    1. Poll Redis queues for new jobs (by tenant)
    2. Pop job from queue (atomic)
    3. Load job from PostgreSQL
    4. Transition status: queued → running
    5. Execute job logic
    6. Transition status: running → finished/failed
    7. Store result in PostgreSQL
    8. Log events for SSE streaming

    Cancellation:
    - Check Redis cancel flag during execution
    - Graceful shutdown on SIGTERM/SIGINT

    Heartbeat:
    - Update job updated_at timestamp periodically
    - Allows detecting stale workers
    """

    def __init__(
        self,
        poll_interval: float = 1.0,
        heartbeat_interval: float = 5.0,
        max_iterations: int | None = None,
    ):
        """
        Initialize worker.

        Args:
            poll_interval: How often to check queues (seconds)
            heartbeat_interval: How often to update job status (seconds)
            max_iterations: Max loop iterations (None = infinite, useful for testing)
        """
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval
        self.max_iterations = max_iterations
        self.running = False
        self.current_job_id: str | None = None

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False

    async def start(self):
        """
        Main worker loop.

        Continuously polls Redis queues and processes jobs.
        """
        logger.info("Jobs worker starting...")
        logger.info(f"Poll interval: {self.poll_interval}s, Heartbeat interval: {self.heartbeat_interval}s")

        self.running = True
        iteration = 0

        while self.running:
            # Check max iterations (for testing)
            if self.max_iterations and iteration >= self.max_iterations:
                logger.info(f"Reached max iterations ({self.max_iterations}), stopping")
                break

            iteration += 1

            try:
                # Process one job from queue
                processed = await self._process_next_job()

                if not processed:
                    # No jobs available, sleep before next poll
                    await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)

        logger.info("Jobs worker stopped")

    async def _process_next_job(self) -> bool:
        """
        Process one job from the queue.

        Polls all allowed job type queues in round-robin fashion.

        Returns:
            True if a job was processed, False if all queues were empty
        """
        # Get allowed job types from settings
        allowed_types_str = getattr(settings, "ALLOWED_JOB_TYPES", "demo,test,long-running")
        allowed_types = [t.strip() for t in allowed_types_str.split(",")]

        # Try to pop from each queue
        for job_type in allowed_types:
            job_id = await asyncio.to_thread(jobs_cache.queue_pop_job, job_type, timeout=0)

            if job_id:
                logger.info(f"Popped job {job_id} from queue '{job_type}'")
                self.current_job_id = job_id

                try:
                    # Get database session
                    db_generator = get_db()
                    db = next(db_generator)

                    try:
                        await self._execute_job(job_id, db)
                    finally:
                        # Clean up database session
                        with contextlib.suppress(StopIteration):
                            next(db_generator)
                        self.current_job_id = None

                except Exception as e:
                    logger.error(f"Failed to execute job {job_id}: {e}", exc_info=True)
                    # Job remains in failed state (set by _execute_job error handling)

                return True

        # All queues were empty
        return False

    async def _execute_job(self, job_id: str, db: Session):
        """
        Execute a single job with full lifecycle management.

        Args:
            job_id: Job UUID as string
            db: SQLAlchemy database session
        """
        job_uuid = UUID(job_id)
        jobs_service = JobsService(db)

        try:
            # Load job from PostgreSQL
            job = jobs_service.repo.get_job(job_uuid)
            if not job:
                logger.error(f"Job {job_id} not found in database")
                return

            logger.info(f"Executing job {job_id}, type={job.type}, status={job.status}")

            # Check if already cancelled
            if await asyncio.to_thread(jobs_cache.check_cancel_flag, job_id):
                logger.info(f"Job {job_id} was cancelled before execution")
                await self._mark_cancelled(job_uuid, jobs_service)
                return

            # Transition to RUNNING
            job = jobs_service.transition_status(job_uuid, from_status="queued", to_status="running")

            if not job:
                logger.error(f"Failed to transition job {job_id} to running (invalid state)")
                return

            # Log event
            jobs_service.append_event(
                job_uuid,
                event_type="status",
                event_data={"to": "running", "from": "queued", "timestamp": datetime.utcnow().isoformat()},
            )

            logger.info(f"Job {job_id} transitioned to RUNNING")

            # Execute job with heartbeat monitoring
            result = await self._run_job_with_heartbeat(job_id, job.type, job.payload_json or {}, jobs_service)

            # Check if cancelled during execution
            if await asyncio.to_thread(jobs_cache.check_cancel_flag, job_id):
                logger.info(f"Job {job_id} was cancelled during execution")
                await self._mark_cancelled(job_uuid, jobs_service)
                return

            # Transition to FINISHED
            job = jobs_service.repo.update_job_result(job_uuid, result)
            job = jobs_service.transition_status(job_uuid, from_status="running", to_status="finished")

            # Log event
            jobs_service.append_event(
                job_uuid,
                event_type="status",
                event_data={"to": "finished", "from": "running", "timestamp": datetime.utcnow().isoformat()},
            )

            logger.info(f"Job {job_id} completed successfully")

        except Exception as e:
            logger.error(f"Job {job_id} failed with error: {e}", exc_info=True)

            # Transition to FAILED
            try:
                job = jobs_service.repo.update_job_error(job_uuid, str(e))
                job = jobs_service.transition_status(job_uuid, from_status="running", to_status="failed")

                # Log event
                jobs_service.append_event(
                    job_uuid,
                    event_type="status",
                    event_data={
                        "to": "failed",
                        "from": "running",
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
            except Exception as transition_error:
                logger.error(f"Failed to mark job {job_id} as failed: {transition_error}")

    async def _run_job_with_heartbeat(
        self, job_id: str, job_type: str, payload: dict[str, Any], jobs_service: JobsService
    ) -> dict[str, Any]:
        """
        Execute job logic with periodic heartbeat updates.

        Args:
            job_id: Job UUID
            job_type: Type of job (demo, test, long-running)
            payload: Job input parameters
            jobs_service: Service instance for database operations

        Returns:
            Job result dictionary
        """
        job_uuid = UUID(job_id)

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(job_uuid, jobs_service))

        try:
            # Execute job based on type
            result = await self._execute_job_type(job_id, job_type, payload)
            return result

        finally:
            # Stop heartbeat
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    async def _heartbeat_loop(self, job_uuid: UUID, jobs_service: JobsService):
        """
        Periodically update job timestamp to indicate worker is alive.

        Args:
            job_uuid: Job UUID
            jobs_service: Service instance
        """
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            try:
                jobs_service.repo.touch_job(job_uuid)
                logger.debug(f"Heartbeat for job {job_uuid}")
            except Exception as e:
                logger.warning(f"Heartbeat failed for job {job_uuid}: {e}")

    async def _execute_job_type(self, job_id: str, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute job logic based on job type.

        Args:
            job_id: Job UUID
            job_type: Job type (demo, test, long-running, agent.run)
            payload: Job configuration

        Returns:
            Result dictionary
        """
        if job_type == "demo":
            return await self._execute_demo_job(job_id, payload)
        elif job_type == "test":
            return await self._execute_test_job(job_id, payload)
        elif job_type == "long-running":
            return await self._execute_long_running_job(job_id, payload)
        elif job_type == "agent.run":
            return await self._execute_agent_run_job(job_id, payload)
        else:
            raise ValueError(f"Unknown job type: {job_type}")

    async def _execute_agent_run_job(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute agent.run job with full orchestrator integration.

        This handler bridges the Jobs system with the Agent Run workflow,
        enabling asynchronous execution of agent tasks with all the same
        features as the synchronous POST /v1/agent-runs endpoint.

        Args:
            job_id: Job UUID
            payload: AgentRunJobPayload fields (prompt, user_id, tenant_id, etc.)

        Returns:
            Result dictionary with orchestration output, metrics, and steps
        """
        start_time = time.time()
        job_uuid = UUID(job_id)
        
        # Extract payload fields (validated against AgentRunJobPayload schema at API layer)
        prompt = payload.get("prompt", "")
        user_id = payload.get("user_id", "unknown")
        tenant_id = payload.get("tenant_id", "default")
        session_id = payload.get("session_id")
        run_id = payload.get("run_id")
        model = payload.get("model")
        manager = payload.get("manager")
        temperature = payload.get("temperature", 0.2)
        max_steps = payload.get("max_steps", 8)
        metadata = payload.get("metadata") or {}
        trace_id = payload.get("trace_id")
        request_id = payload.get("request_id")
        principal = payload.get("principal")

        logger.info(
            f"Agent.run job {job_id}: starting orchestration",
            extra={
                "user_id": user_id,
                "tenant_id": tenant_id,
                "session_id": session_id,
                "run_id": run_id,
                "prompt_length": len(prompt),
            },
        )

        # Get database session for AgentRun operations
        db_generator = get_db()
        db = next(db_generator)
        agent_run = None
        
        try:
            # Import repositories for AgentRun management
            from db.postgres_control.repositories.agents import AgentRunRepository

            # ──────────────────────────────────────────────────────────────────
            # Step 1: Create or load AgentRun record
            # ──────────────────────────────────────────────────────────────────
            if run_id:
                # Load existing AgentRun if pre-created
                agent_run = AgentRunRepository.get_by_id(db, UUID(run_id))
                if agent_run:
                    logger.info(f"Loaded existing AgentRun {run_id} for job {job_id}")
                else:
                    logger.warning(f"AgentRun {run_id} not found, creating new one")
                    run_id = None

            if not agent_run:
                # Create new AgentRun record with status=running
                agent_run = AgentRunRepository.create(
                    db,
                    session_id=UUID(session_id) if session_id else None,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    model=model,
                    manager=manager,
                    trace_id=trace_id,
                    request_id=request_id,
                    status="running",
                    metadata={
                        **metadata,
                        "job_id": job_id,  # Link to parent job
                        "execution_mode": "async",
                    },
                )
                run_id = str(agent_run.run_id)
                db.commit()
                logger.info(f"Created AgentRun {run_id} for job {job_id}")

            # Update AgentRun status to running if not already
            if agent_run.status != "running":
                AgentRunRepository.update_status(db, agent_run.run_id, status="running")
                db.commit()

            # Emit progress event: AgentRun created/started
            await self._emit_progress_event(
                job_id,
                event_type="progress",
                data={
                    "stage": "agent_run_started",
                    "run_id": run_id,
                    "message": "Agent run initialized",
                },
            )

            # ──────────────────────────────────────────────────────────────────
            # Step 2: Initialize Orchestrator
            # ──────────────────────────────────────────────────────────────────
            from src.services.orchestrator import Orchestrator, RUN_TIMEOUT_SECONDS

            # Emit progress event: Orchestrator initialization
            await self._emit_progress_event(
                job_id,
                event_type="progress",
                data={"stage": "orchestrator_init", "message": "Initializing orchestrator"},
            )

            # Check cancellation before heavy initialization
            if await asyncio.to_thread(jobs_cache.check_cancel_flag, job_id):
                raise asyncio.CancelledError("Job cancelled before orchestrator init")

            orch = Orchestrator.from_env()
            logger.info(f"Orchestrator initialized for job {job_id}")

            # ──────────────────────────────────────────────────────────────────
            # Step 3: Build orchestrator params (like agent_runs.py does)
            # ──────────────────────────────────────────────────────────────────
            params = {
                "temperature": temperature,
                "max_steps": max_steps,
                "principal": principal,
                "job_id": job_id,  # Allow orchestrator to know it's in job context
            }
            if model:
                params["model"] = model
            if manager:
                params["manager"] = manager

            # Emit progress event: Starting orchestration
            await self._emit_progress_event(
                job_id,
                event_type="progress",
                data={"stage": "orchestration_start", "message": "Starting orchestration"},
            )

            # ──────────────────────────────────────────────────────────────────
            # Step 4: Execute orchestrator.run() with timeout
            # ──────────────────────────────────────────────────────────────────
            result = None
            orchestration_error = None
            
            try:
                result = await asyncio.wait_for(
                    orch.run(
                        goal=prompt,
                        user_id=user_id,
                        session_id=session_id,
                        tenant_id=tenant_id,
                        run_id=run_id,
                        principal=principal,
                        params=params,
                    ),
                    timeout=RUN_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                orchestration_error = f"Orchestration timed out after {RUN_TIMEOUT_SECONDS}s"
                logger.error(f"Job {job_id}: {orchestration_error}")
            except asyncio.CancelledError:
                orchestration_error = "Job cancelled during orchestration"
                logger.info(f"Job {job_id}: {orchestration_error}")
                raise  # Re-raise to trigger proper cancellation handling
            except Exception as e:
                orchestration_error = str(e)
                logger.error(f"Job {job_id} orchestration error: {e}", exc_info=True)

            # Check cancellation after orchestration
            if await asyncio.to_thread(jobs_cache.check_cancel_flag, job_id):
                raise asyncio.CancelledError("Job cancelled after orchestration")

            # ──────────────────────────────────────────────────────────────────
            # Step 5: Process orchestration result
            # ──────────────────────────────────────────────────────────────────
            output_text = ""
            todos_data = []
            steps_data = []
            warnings_list = []
            metrics_data = {}
            success = False

            if result and result.data:
                output_text = str(result.data.get("output", ""))
                success = bool(result.ok)
                
                # Extract metrics
                raw_metrics = result.data.get("metrics")
                if isinstance(raw_metrics, dict):
                    metrics_data = dict(raw_metrics)
                
                # Extract TODOs
                raw_todos = result.data.get("todos", [])
                for todo in raw_todos:
                    if isinstance(todo, dict):
                        todos_data.append(todo)
                    elif isinstance(todo, str):
                        todos_data.append({"task": todo})

                # Extract steps
                orchestration_steps = result.data.get("steps", [])
                for step in orchestration_steps:
                    steps_data.append(step)

                # Extract warnings
                warnings_list = result.data.get("warnings", [])

                if not result.ok:
                    orchestration_error = str(result.error) if result.error else "Orchestration failed"

            elif orchestration_error:
                success = False
            else:
                success = False
                orchestration_error = "No result from orchestrator"

            # Emit progress event: Orchestration complete
            await self._emit_progress_event(
                job_id,
                event_type="progress",
                data={
                    "stage": "orchestration_complete",
                    "success": success,
                    "steps_count": len(steps_data),
                    "todos_count": len(todos_data),
                },
            )

            # ──────────────────────────────────────────────────────────────────
            # Step 6: Apply PII scrubbing
            # ──────────────────────────────────────────────────────────────────
            if PII_SCRUBBER_AVAILABLE and pii_scrub_dict:
                try:
                    # Scrub output text
                    from src.security.pii_scrubber import scrub_text
                    output_text = scrub_text(output_text)
                    
                    # Scrub structured data
                    for todo in todos_data:
                        if isinstance(todo, dict):
                            pii_scrub_dict(todo)
                    for step in steps_data:
                        if isinstance(step, dict):
                            pii_scrub_dict(step)
                    
                    logger.debug(f"PII scrubbing applied to job {job_id} results")
                except Exception as e:
                    logger.warning(f"PII scrubbing failed for job {job_id}: {e}")
                    warnings_list.append(f"PII scrubbing error: {e}")

            # ──────────────────────────────────────────────────────────────────
            # Step 7: Apply output guard validation
            # ──────────────────────────────────────────────────────────────────
            if OUTPUT_GUARD_AVAILABLE and guard_text:
                try:
                    guard_result = guard_text(output_text)
                    if hasattr(guard_result, 'allowed') and not guard_result.allowed:
                        logger.warning(f"Output guard blocked result for job {job_id}")
                        output_text = "[Output blocked by security policy]"
                        warnings_list.append("Output modified by security guard")
                except Exception as e:
                    logger.warning(f"Output guard check failed for job {job_id}: {e}")

            # ──────────────────────────────────────────────────────────────────
            # Step 8: Emit agent metrics
            # ──────────────────────────────────────────────────────────────────
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            if AGENT_METRICS_AVAILABLE and agent_metrics:
                try:
                    status_label = "success" if success else "failure"
                    agent_metrics.agent_run_duration_seconds.labels(
                        status=status_label,
                        tenant_id=tenant_id,
                    ).observe(elapsed_ms / 1000.0)
                    
                    if success:
                        agent_metrics.agent_run_success_total.labels(
                            tenant_id=tenant_id,
                        ).inc()
                    else:
                        agent_metrics.agent_run_failures_total.labels(
                            failure_type="orchestration_error" if orchestration_error else "unknown",
                            tenant_id=tenant_id,
                        ).inc()
                    
                    # Record TODO count
                    if todos_data:
                        agent_metrics.agent_todos_count.labels(
                            tenant_id=tenant_id,
                        ).observe(len(todos_data))
                        
                except Exception as e:
                    logger.warning(f"Failed to emit agent metrics for job {job_id}: {e}")

            # ──────────────────────────────────────────────────────────────────
            # Step 9: Update AgentRun with final state (sync with Job)
            # ──────────────────────────────────────────────────────────────────
            final_status = "succeeded" if success else "failed"
            
            AgentRunRepository.update_status(
                db,
                agent_run.run_id,
                status=final_status,
                latency_ms=elapsed_ms,
                finished_at=datetime.now(timezone.utc),
                model=model or orch.default_model,
                output={"text": output_text} if output_text else None,
                todos=todos_data,
                steps=steps_data,
                warnings=warnings_list,
                metrics=metrics_data,
            )
            db.commit()
            
            logger.info(
                f"AgentRun {run_id} updated to {final_status} for job {job_id}",
                extra={"elapsed_ms": elapsed_ms, "success": success},
            )

            # Emit final progress event
            await self._emit_progress_event(
                job_id,
                event_type="progress",
                data={
                    "stage": "completed",
                    "run_id": run_id,
                    "status": final_status,
                    "elapsed_ms": elapsed_ms,
                },
            )

            # ──────────────────────────────────────────────────────────────────
            # Step 10: Build and return result
            # ──────────────────────────────────────────────────────────────────
            job_result = {
                "status": "completed" if success else "failed",
                "run_id": run_id,
                "output": output_text,
                "todos": todos_data,
                "steps": steps_data,
                "warnings": warnings_list,
                "metrics": metrics_data,
                "elapsed_ms": elapsed_ms,
                "model": model or orch.default_model,
            }
            
            if orchestration_error and not success:
                job_result["error"] = orchestration_error
                raise RuntimeError(orchestration_error)  # Trigger job failure

            return job_result

        except asyncio.CancelledError:
            # Handle cancellation - update AgentRun state
            elapsed_ms = int((time.time() - start_time) * 1000)
            if agent_run:
                try:
                    AgentRunRepository.update_status(
                        db,
                        agent_run.run_id,
                        status="cancelled",
                        latency_ms=elapsed_ms,
                        finished_at=datetime.now(timezone.utc),
                    )
                    db.commit()
                except Exception as e:
                    logger.error(f"Failed to mark AgentRun as cancelled: {e}")
            raise

        except Exception as e:
            # Handle errors - update AgentRun state
            elapsed_ms = int((time.time() - start_time) * 1000)
            if agent_run:
                try:
                    AgentRunRepository.update_status(
                        db,
                        agent_run.run_id,
                        status="failed",
                        latency_ms=elapsed_ms,
                        finished_at=datetime.now(timezone.utc),
                    )
                    db.commit()
                except Exception as update_error:
                    logger.error(f"Failed to mark AgentRun as failed: {update_error}")
            raise

        finally:
            # Clean up database session
            with contextlib.suppress(StopIteration):
                next(db_generator)

    async def _emit_progress_event(
        self,
        job_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """
        Emit a progress event to Redis for SSE streaming.

        Args:
            job_id: Job UUID
            event_type: Event type (progress, log, etc.)
            data: Event data payload
        """
        try:
            event_data = {
                **data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await asyncio.to_thread(
                jobs_cache.append_event,
                job_id,
                event_type,
                event_data,
            )
        except Exception as e:
            logger.warning(f"Failed to emit progress event for job {job_id}: {e}")

    async def _execute_demo_job(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute demo job (simple sleep simulation).

        Args:
            job_id: Job UUID
            payload: May contain 'duration_ms' key

        Returns:
            Result with execution time
        """
        duration_ms = payload.get("duration_ms", 1000)
        duration_sec = duration_ms / 1000.0

        logger.info(f"Demo job {job_id}: sleeping for {duration_sec}s")

        # Simulate work with cancellation checks
        start = time.time()
        sleep_chunks = int(duration_sec / 0.5) + 1  # Check every 0.5s

        for _ in range(sleep_chunks):
            if await asyncio.to_thread(jobs_cache.check_cancel_flag, job_id):
                raise asyncio.CancelledError("Job cancelled")
            await asyncio.sleep(min(0.5, duration_sec))

        elapsed = time.time() - start

        return {
            "status": "completed",
            "requested_duration_ms": duration_ms,
            "actual_duration_ms": int(elapsed * 1000),
            "message": "Demo job completed successfully",
        }

    async def _execute_test_job(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute test job (instant completion with echo).

        Args:
            job_id: Job UUID
            payload: Arbitrary test data

        Returns:
            Echo of input payload
        """
        logger.info(f"Test job {job_id}: echoing payload")

        return {
            "status": "completed",
            "input": payload,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Test job completed",
        }

    async def _execute_long_running_job(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute long-running job (30+ seconds with progress updates).

        Args:
            job_id: Job UUID
            payload: May contain 'steps' key (default 10)

        Returns:
            Result with step count
        """
        steps = payload.get("steps", 10)
        step_duration = 3.0  # 3 seconds per step

        logger.info(f"Long-running job {job_id}: {steps} steps, {steps * step_duration}s total")

        for step in range(1, steps + 1):
            if await asyncio.to_thread(jobs_cache.check_cancel_flag, job_id):
                raise asyncio.CancelledError("Job cancelled")

            logger.info(f"Job {job_id}: step {step}/{steps}")
            await asyncio.sleep(step_duration)

        return {
            "status": "completed",
            "steps_completed": steps,
            "total_duration_ms": int(steps * step_duration * 1000),
            "message": f"Completed {steps} steps",
        }

    async def _mark_cancelled(self, job_uuid: UUID, jobs_service: JobsService):
        """
        Mark job as cancelled.

        Args:
            job_uuid: Job UUID
            jobs_service: Service instance
        """
        try:
            # Try from queued
            job = jobs_service.transition_status(job_uuid, from_status="queued", to_status="cancelled")

            if not job:
                # Try from running
                job = jobs_service.transition_status(job_uuid, from_status="running", to_status="cancelled")

            if job:
                jobs_service.append_event(
                    job_uuid,
                    event_type="status",
                    event_data={"to": "cancelled", "timestamp": datetime.utcnow().isoformat()},
                )
                logger.info(f"Job {job_uuid} marked as cancelled")
        except Exception as e:
            logger.error(f"Failed to mark job {job_uuid} as cancelled: {e}")


async def main():
    """Main entry point for worker process."""
    # Get configuration from environment
    poll_interval = float(getattr(settings, "JOB_WORKER_POLL_INTERVAL", 1.0))
    heartbeat_interval = float(getattr(settings, "JOB_WORKER_HEARTBEAT_INTERVAL", 5.0))

    # Check if PostgreSQL backend is enabled
    use_postgres_value = getattr(settings, "USE_POSTGRES_JOBS", False)
    if isinstance(use_postgres_value, bool):
        use_postgres = use_postgres_value
    else:
        use_postgres = str(use_postgres_value).lower() in ("true", "1", "yes")

    if not use_postgres:
        logger.error("Worker requires USE_POSTGRES_JOBS=true")
        sys.exit(1)

    logger.info("Starting PostgreSQL-backed jobs worker")
    logger.info(f"Database URL: {settings.database_url}")
    logger.info(f"Redis URL: {settings.REDIS_URL}")

    # Create and start worker
    worker = JobsWorker(poll_interval=poll_interval, heartbeat_interval=heartbeat_interval)

    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Run worker
    asyncio.run(main())
