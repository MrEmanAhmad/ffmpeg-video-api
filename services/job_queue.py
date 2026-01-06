"""
In-memory job queue for background video processing
"""
import uuid
import logging
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Callable, Any
from enum import Enum
import config

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job status enumeration"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Job:
    """Represents a video rendering job"""
    
    def __init__(self, job_id: str, template_id: str, request_data: dict):
        self.job_id = job_id
        self.template_id = template_id
        self.request_data = request_data
        self.status = JobStatus.QUEUED
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.output_path: Optional[str] = None
        self.file_size_bytes: Optional[int] = None
        self.duration_seconds: Optional[float] = None
        self.error_message: Optional[str] = None
        self.error_code: Optional[str] = None
        self.progress: int = 0  # 0-100
    
    def to_dict(self) -> dict:
        """Convert job to dictionary for API response"""
        result = {
            "job_id": self.job_id,
            "template_id": self.template_id,
            "status": self.status.value,
            "progress": self.progress,
            "created_at": self.created_at.isoformat() + "Z",
        }
        
        if self.started_at:
            result["started_at"] = self.started_at.isoformat() + "Z"
        
        if self.completed_at:
            result["completed_at"] = self.completed_at.isoformat() + "Z"
        
        if self.status == JobStatus.COMPLETED:
            result["download_url"] = f"/download/{self.job_id}"
            if self.file_size_bytes:
                result["file_size_mb"] = round(self.file_size_bytes / (1024 * 1024), 2)
            if self.duration_seconds:
                result["duration_seconds"] = self.duration_seconds
        
        if self.status == JobStatus.FAILED:
            result["error"] = {
                "message": self.error_message,
                "code": self.error_code
            }
        
        return result


class JobQueue:
    """In-memory job queue with ThreadPoolExecutor"""
    
    def __init__(
        self,
        max_workers: int = None,
        max_queue_size: int = None
    ):
        """
        Initialize job queue
        
        Args:
            max_workers: Maximum concurrent jobs
            max_queue_size: Maximum pending jobs in queue
        """
        self.max_workers = max_workers or config.MAX_CONCURRENT_JOBS
        self.max_queue_size = max_queue_size or config.MAX_QUEUE_SIZE
        
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._processor: Optional[Callable] = None
        
        logger.info(f"JobQueue initialized: max_workers={self.max_workers}, max_queue={self.max_queue_size}")
    
    def set_processor(self, processor: Callable[[Job], None]):
        """
        Set the job processor function
        
        Args:
            processor: Function that processes a job
        """
        self._processor = processor
    
    def submit_job(self, template_id: str, request_data: dict) -> Job:
        """
        Submit a new job to the queue
        
        Args:
            template_id: Template to use for rendering
            request_data: Request data including images
            
        Returns:
            Created job
            
        Raises:
            ValueError: If queue is full
        """
        with self._lock:
            # Check queue size
            pending_count = sum(
                1 for j in self._jobs.values()
                if j.status in (JobStatus.QUEUED, JobStatus.PROCESSING)
            )
            
            if pending_count >= self.max_queue_size:
                raise ValueError(
                    f"Queue is full. Maximum {self.max_queue_size} pending jobs allowed."
                )
            
            # Create job
            job_id = str(uuid.uuid4())
            job = Job(job_id, template_id, request_data)
            self._jobs[job_id] = job
            
            logger.info(f"Job submitted: {job_id}")
        
        # Submit to executor
        if self._processor:
            self._executor.submit(self._process_job, job_id)
        else:
            logger.warning("No processor set, job will remain queued")
        
        return job
    
    def _process_job(self, job_id: str):
        """
        Internal method to process a job
        
        Args:
            job_id: Job ID to process
        """
        job = self.get_job(job_id)
        if not job:
            logger.error(f"Job not found: {job_id}")
            return
        
        # Update status to processing
        with self._lock:
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.utcnow()
        
        logger.info(f"Processing job: {job_id}")
        
        try:
            # Call the processor
            self._processor(job)
            
            # Mark as completed if processor didn't set status
            with self._lock:
                if job.status == JobStatus.PROCESSING:
                    job.status = JobStatus.COMPLETED
                    job.completed_at = datetime.utcnow()
                    job.progress = 100
            
            logger.info(f"Job completed: {job_id}")
            
        except Exception as e:
            logger.error(f"Job failed: {job_id} - {str(e)}")
            
            with self._lock:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.utcnow()
                job.error_message = str(e)
                job.error_code = "PROCESSING_ERROR"
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """
        Get a job by ID
        
        Args:
            job_id: Job ID
            
        Returns:
            Job or None if not found
        """
        return self._jobs.get(job_id)
    
    def get_active_jobs(self) -> list:
        """
        Get all active (queued or processing) jobs
        
        Returns:
            List of active jobs
        """
        with self._lock:
            return [
                j for j in self._jobs.values()
                if j.status in (JobStatus.QUEUED, JobStatus.PROCESSING)
            ]
    
    def get_all_jobs(self) -> list:
        """
        Get all jobs
        
        Returns:
            List of all jobs
        """
        return list(self._jobs.values())
    
    def get_stats(self) -> dict:
        """
        Get queue statistics
        
        Returns:
            Dictionary with queue stats
        """
        with self._lock:
            jobs = list(self._jobs.values())
        
        return {
            "total_jobs": len(jobs),
            "queued": sum(1 for j in jobs if j.status == JobStatus.QUEUED),
            "processing": sum(1 for j in jobs if j.status == JobStatus.PROCESSING),
            "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
            "max_workers": self.max_workers,
            "max_queue_size": self.max_queue_size
        }
    
    def update_job_progress(self, job_id: str, progress: int):
        """
        Update job progress
        
        Args:
            job_id: Job ID
            progress: Progress percentage (0-100)
        """
        job = self.get_job(job_id)
        if job:
            with self._lock:
                job.progress = min(100, max(0, progress))
    
    def mark_job_completed(
        self,
        job_id: str,
        output_path: str,
        file_size_bytes: int = None,
        duration_seconds: float = None
    ):
        """
        Mark a job as completed
        
        Args:
            job_id: Job ID
            output_path: Path to output video
            file_size_bytes: Output file size
            duration_seconds: Video duration
        """
        job = self.get_job(job_id)
        if job:
            with self._lock:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                job.output_path = output_path
                job.file_size_bytes = file_size_bytes
                job.duration_seconds = duration_seconds
                job.progress = 100
    
    def mark_job_failed(self, job_id: str, error_message: str, error_code: str = "PROCESSING_ERROR"):
        """
        Mark a job as failed
        
        Args:
            job_id: Job ID
            error_message: Error description
            error_code: Error code
        """
        job = self.get_job(job_id)
        if job:
            with self._lock:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.utcnow()
                job.error_message = error_message
                job.error_code = error_code
    
    def cleanup_old_jobs(self, hours: int = 24) -> int:
        """
        Remove old completed/failed jobs from memory
        
        Args:
            hours: Age threshold in hours
            
        Returns:
            Number of jobs removed
        """
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        removed = 0
        
        with self._lock:
            jobs_to_remove = [
                job_id for job_id, job in self._jobs.items()
                if job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
                and job.completed_at and job.completed_at < cutoff
            ]
            
            for job_id in jobs_to_remove:
                del self._jobs[job_id]
                removed += 1
        
        if removed:
            logger.info(f"Cleaned up {removed} old jobs")
        
        return removed
    
    def shutdown(self, wait: bool = True):
        """
        Shutdown the executor
        
        Args:
            wait: Whether to wait for pending jobs to complete
        """
        logger.info("Shutting down job queue...")
        self._executor.shutdown(wait=wait)


# Global job queue instance
job_queue = JobQueue()

