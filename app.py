"""
FFmpeg Video Template API
A Flask-based API for creating videos from image sequences using FFmpeg
"""
import os
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import after logging is configured
import config
from services.template_service import template_service
from services.job_queue import job_queue, JobStatus
from services.video_service import video_service
from utils.validators import ValidationError, validate_template_structure, validate_render_request
from utils.ffmpeg_builder import check_ffmpeg_installed, get_ffmpeg_version
from utils.cleanup import cleanup_old_videos, get_temp_dir_stats

# Create Flask app
app = Flask(__name__)
CORS(app)

# Run cleanup on startup
logger.info("Running startup cleanup...")
cleanup_result = cleanup_old_videos()
logger.info(f"Startup cleanup: {cleanup_result['cleaned_count']} files removed")


def error_response(message: str, code: str, status_code: int = 400, details: dict = None):
    """Create consistent error response"""
    return jsonify({
        "error": True,
        "message": message,
        "code": code,
        "details": details or {}
    }), status_code


# =============================================================================
# Health Check Endpoint
# =============================================================================

@app.route('/')
def health():
    """Health check endpoint with service status"""
    ffmpeg_installed = check_ffmpeg_installed()
    ffmpeg_version = get_ffmpeg_version() if ffmpeg_installed else None
    queue_stats = job_queue.get_stats()
    templates = template_service.list_templates()
    temp_stats = get_temp_dir_stats()
    
    return jsonify({
        "status": "online",
        "service": "FFmpeg Video API",
        "version": "1.0.0",
        "ffmpeg": {
            "installed": ffmpeg_installed,
            "version": ffmpeg_version
        },
        "queue": {
            "active_jobs": queue_stats["queued"] + queue_stats["processing"],
            "processing": queue_stats["processing"],
            "queued": queue_stats["queued"],
            "max_concurrent": queue_stats["max_workers"]
        },
        "templates": {
            "count": len(templates),
            "available": [t["template_name"] for t in templates]
        },
        "storage": {
            "temp_files": temp_stats["total_files"],
            "temp_size_mb": temp_stats["total_size_mb"]
        }
    })


# =============================================================================
# Template Endpoints
# =============================================================================

@app.route('/create-template', methods=['POST'])
def create_template():
    """Create a new video template"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response(
                "Request body is required",
                "INVALID_REQUEST"
            )
        
        # Validate template structure
        validate_template_structure(data)
        
        # Create template
        result = template_service.create_template(data)
        
        logger.info(f"Template created: {result['template_name']}")
        return jsonify(result), 201
        
    except ValidationError as e:
        return error_response(e.message, e.code, details=e.details)
    except ValueError as e:
        return error_response(str(e), "TEMPLATE_EXISTS", 409)
    except Exception as e:
        logger.error(f"Error creating template: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


@app.route('/templates', methods=['GET'])
def list_templates():
    """List all available templates"""
    try:
        templates = template_service.list_templates()
        return jsonify({
            "templates": templates,
            "count": len(templates)
        })
    except Exception as e:
        logger.error(f"Error listing templates: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


@app.route('/templates/<template_id>', methods=['GET'])
def get_template(template_id):
    """Get a specific template by ID"""
    try:
        template = template_service.get_template(template_id)
        
        if not template:
            return error_response(
                f"Template not found: {template_id}",
                "TEMPLATE_NOT_FOUND",
                404
            )
        
        return jsonify(template)
        
    except ValidationError as e:
        return error_response(e.message, e.code, details=e.details)
    except Exception as e:
        logger.error(f"Error getting template: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


@app.route('/templates/<template_id>', methods=['DELETE'])
def delete_template(template_id):
    """Delete a template"""
    try:
        deleted = template_service.delete_template(template_id)
        
        if not deleted:
            return error_response(
                f"Template not found: {template_id}",
                "TEMPLATE_NOT_FOUND",
                404
            )
        
        logger.info(f"Template deleted: {template_id}")
        return jsonify({
            "status": "success",
            "message": f"Template {template_id} deleted"
        })
        
    except ValueError as e:
        return error_response(str(e), "CANNOT_DELETE", 403)
    except ValidationError as e:
        return error_response(e.message, e.code, details=e.details)
    except Exception as e:
        logger.error(f"Error deleting template: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


# =============================================================================
# Video Rendering Endpoints
# =============================================================================

@app.route('/render-video', methods=['POST'])
def render_video():
    """Submit a video rendering job"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response(
                "Request body is required",
                "INVALID_REQUEST"
            )
        
        # Get template ID
        template_id = data.get("template_id")
        if not template_id:
            return error_response(
                "template_id is required",
                "INVALID_REQUEST"
            )
        
        # Verify template exists
        template = template_service.get_template(template_id)
        if not template:
            return error_response(
                f"Template not found: {template_id}",
                "TEMPLATE_NOT_FOUND",
                404
            )
        
        # Validate request against template
        validate_render_request(data, template)
        
        # Check FFmpeg availability
        if not check_ffmpeg_installed():
            return error_response(
                "FFmpeg is not installed on this server",
                "FFMPEG_NOT_AVAILABLE",
                503
            )
        
        # Submit job to queue
        job = job_queue.submit_job(template_id, data)
        
        # Calculate estimated time based on template duration
        total_duration = sum(
            segment.get("duration", 0)
            for scene in template.get("scenes", [])
            for segment in scene.get("segments", [])
        )
        estimated_time = max(30, total_duration)  # At least 30 seconds
        
        logger.info(f"Render job submitted: {job.job_id}")
        
        return jsonify({
            "status": "processing",
            "job_id": job.job_id,
            "template_id": template_id,
            "estimated_time_seconds": estimated_time,
            "check_status_url": f"/status/{job.job_id}"
        }), 202
        
    except ValidationError as e:
        return error_response(e.message, e.code, details=e.details)
    except ValueError as e:
        # Queue full
        return error_response(str(e), "QUEUE_FULL", 503)
    except Exception as e:
        logger.error(f"Error submitting render job: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get status of a rendering job"""
    try:
        job = job_queue.get_job(job_id)
        
        if not job:
            return error_response(
                f"Job not found: {job_id}",
                "JOB_NOT_FOUND",
                404
            )
        
        return jsonify(job.to_dict())
        
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


@app.route('/download/<job_id>', methods=['GET'])
def download_video(job_id):
    """Download rendered video"""
    try:
        job = job_queue.get_job(job_id)
        
        if not job:
            return error_response(
                f"Job not found: {job_id}",
                "JOB_NOT_FOUND",
                404
            )
        
        if job.status != JobStatus.COMPLETED:
            return error_response(
                f"Video not ready. Current status: {job.status.value}",
                "VIDEO_NOT_READY",
                400
            )
        
        # Get video path
        video_path = video_service.get_video_path(job_id)
        
        if not video_path or not video_path.exists():
            return error_response(
                "Video file not found. It may have been cleaned up.",
                "VIDEO_NOT_FOUND",
                404
            )
        
        logger.info(f"Serving video download: {job_id}")
        
        return send_file(
            video_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f'video_{job_id}.mp4'
        )
        
    except Exception as e:
        logger.error(f"Error downloading video: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


# =============================================================================
# Utility Endpoints
# =============================================================================

@app.route('/cleanup', methods=['POST'])
def cleanup():
    """Clean up old video files"""
    try:
        hours = request.args.get('hours', config.VIDEO_RETENTION_HOURS, type=int)
        result = cleanup_old_videos(hours)
        
        # Also cleanup old jobs from memory
        jobs_cleaned = job_queue.cleanup_old_jobs(hours)
        result["jobs_cleaned"] = jobs_cleaned
        
        logger.info(f"Cleanup completed: {result}")
        
        return jsonify({
            "status": "success",
            **result
        })
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


@app.route('/jobs', methods=['GET'])
def list_jobs():
    """List all jobs (for debugging/monitoring)"""
    try:
        jobs = job_queue.get_all_jobs()
        stats = job_queue.get_stats()
        
        return jsonify({
            "jobs": [job.to_dict() for job in jobs],
            "stats": stats
        })
        
    except Exception as e:
        logger.error(f"Error listing jobs: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


# =============================================================================
# Error Handlers
# =============================================================================

@app.errorhandler(404)
def not_found(e):
    return error_response("Endpoint not found", "NOT_FOUND", 404)


@app.errorhandler(405)
def method_not_allowed(e):
    return error_response("Method not allowed", "METHOD_NOT_ALLOWED", 405)


@app.errorhandler(500)
def internal_error(e):
    return error_response("Internal server error", "SERVER_ERROR", 500)


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == '__main__':
    port = config.PORT
    debug = config.DEBUG
    
    logger.info(f"Starting FFmpeg Video API on port {port}")
    logger.info(f"FFmpeg installed: {check_ffmpeg_installed()}")
    logger.info(f"Templates available: {len(template_service.list_templates())}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)

