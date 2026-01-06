"""
Cleanup utilities for managing temporary video files
"""
import os
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
import config

logger = logging.getLogger(__name__)


def cleanup_old_videos(retention_hours: int = None) -> dict:
    """
    Delete videos older than retention period
    
    Args:
        retention_hours: Hours to retain videos (default from config)
        
    Returns:
        Dictionary with cleanup statistics
    """
    retention_hours = retention_hours or config.VIDEO_RETENTION_HOURS
    cutoff_time = time.time() - (retention_hours * 3600)
    
    cleaned_count = 0
    cleaned_size = 0
    errors = []
    
    temp_dir = config.TEMP_DIR
    
    if not temp_dir.exists():
        logger.info(f"Temp directory does not exist: {temp_dir}")
        return {
            "cleaned_count": 0,
            "cleaned_size_mb": 0,
            "errors": []
        }
    
    # Clean up video files
    for file_path in temp_dir.glob("**/*"):
        if not file_path.is_file():
            continue
            
        try:
            file_stat = file_path.stat()
            
            # Check if file is older than retention period
            if file_stat.st_mtime < cutoff_time:
                file_size = file_stat.st_size
                file_path.unlink()
                cleaned_count += 1
                cleaned_size += file_size
                logger.info(f"Deleted old file: {file_path}")
                
        except Exception as e:
            error_msg = f"Error deleting {file_path}: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)
    
    # Clean up empty directories
    for dir_path in sorted(temp_dir.glob("**/*"), reverse=True):
        if dir_path.is_dir():
            try:
                dir_path.rmdir()  # Only removes if empty
                logger.info(f"Removed empty directory: {dir_path}")
            except OSError:
                pass  # Directory not empty, skip
    
    result = {
        "cleaned_count": cleaned_count,
        "cleaned_size_mb": round(cleaned_size / (1024 * 1024), 2),
        "errors": errors
    }
    
    logger.info(f"Cleanup complete: {cleaned_count} files, {result['cleaned_size_mb']} MB")
    return result


def cleanup_job_files(job_id: str) -> bool:
    """
    Clean up all files associated with a specific job
    
    Args:
        job_id: The job ID to clean up
        
    Returns:
        True if cleanup successful, False otherwise
    """
    job_dir = config.TEMP_DIR / job_id
    
    if not job_dir.exists():
        return True
    
    try:
        # Remove all files in job directory
        for file_path in job_dir.glob("*"):
            if file_path.is_file():
                file_path.unlink()
        
        # Remove the job directory
        job_dir.rmdir()
        logger.info(f"Cleaned up job directory: {job_dir}")
        return True
        
    except Exception as e:
        logger.error(f"Error cleaning up job {job_id}: {str(e)}")
        return False


def get_temp_dir_stats() -> dict:
    """
    Get statistics about the temp directory
    
    Returns:
        Dictionary with temp directory statistics
    """
    temp_dir = config.TEMP_DIR
    
    if not temp_dir.exists():
        return {
            "total_files": 0,
            "total_size_mb": 0,
            "oldest_file_hours": None
        }
    
    total_files = 0
    total_size = 0
    oldest_time = None
    
    for file_path in temp_dir.glob("**/*"):
        if file_path.is_file():
            total_files += 1
            stat = file_path.stat()
            total_size += stat.st_size
            
            if oldest_time is None or stat.st_mtime < oldest_time:
                oldest_time = stat.st_mtime
    
    oldest_hours = None
    if oldest_time:
        oldest_hours = round((time.time() - oldest_time) / 3600, 1)
    
    return {
        "total_files": total_files,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "oldest_file_hours": oldest_hours
    }

