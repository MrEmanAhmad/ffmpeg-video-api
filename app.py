"""
FFmpeg Video Template API
A Flask-based API for creating videos from image sequences using FFmpeg
"""
import os
import logging
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from flasgger import Swagger, swag_from
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
from utils.validators import (
    ValidationError, 
    validate_template_structure, 
    validate_render_request,
    validate_audio_settings,
    validate_webhook_url,
    validate_render_mode
)
from utils.ffmpeg_builder import check_ffmpeg_installed, get_ffmpeg_version
from utils.cleanup import cleanup_old_videos, get_temp_dir_stats

# Create Flask app
app = Flask(__name__)
CORS(app)

# Swagger configuration
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "FFmpeg Video Template API",
        "description": "Create videos from image sequences using FFmpeg with reusable templates",
        "version": "2.0.0",
        "contact": {
            "name": "API Support"
        }
    },
    "securityDefinitions": {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key for authentication (required when AUTH_ENABLED=true)"
        }
    },
    "security": [{"ApiKeyAuth": []}],
    "tags": [
        {"name": "Health", "description": "Service health and status"},
        {"name": "Templates", "description": "Template management endpoints"},
        {"name": "Rendering", "description": "Video rendering endpoints"},
        {"name": "Utility", "description": "Utility endpoints"}
    ]
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

# Run cleanup on startup
logger.info("Running startup cleanup...")
cleanup_result = cleanup_old_videos()
logger.info(f"Startup cleanup: {cleanup_result['cleaned_count']} files removed")

# Log auth status
if config.AUTH_ENABLED:
    logger.info(f"API Key authentication ENABLED ({len(config.API_KEYS)} keys configured)")
else:
    logger.info("API Key authentication DISABLED (no API_KEYS configured)")


# =============================================================================
# Authentication
# =============================================================================

def require_api_key(f):
    """Decorator to require API key authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not config.AUTH_ENABLED:
            return f(*args, **kwargs)
        
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return error_response(
                "API key required. Provide X-API-Key header.",
                "UNAUTHORIZED",
                401
            )
        
        if api_key not in config.API_KEYS:
            return error_response(
                "Invalid API key",
                "UNAUTHORIZED",
                401
            )
        
        return f(*args, **kwargs)
    return decorated_function


def error_response(message: str, code: str, status_code: int = 400, details: dict = None):
    """Create consistent error response"""
    return jsonify({
        "error": True,
        "message": message,
        "code": code,
        "details": details or {}
    }), status_code


# =============================================================================
# Health Check Endpoint (Public)
# =============================================================================

@app.route('/')
def health():
    """
    Health check endpoint
    ---
    tags:
      - Health
    responses:
      200:
        description: Service status and information
        schema:
          type: object
          properties:
            status:
              type: string
              example: online
            service:
              type: string
              example: FFmpeg Video API
            version:
              type: string
              example: "2.0.0"
            auth_enabled:
              type: boolean
            ffmpeg:
              type: object
              properties:
                installed:
                  type: boolean
                version:
                  type: string
            queue:
              type: object
              properties:
                active_jobs:
                  type: integer
                processing:
                  type: integer
                queued:
                  type: integer
                max_concurrent:
                  type: integer
            templates:
              type: object
              properties:
                count:
                  type: integer
                available:
                  type: array
                  items:
                    type: string
    """
    ffmpeg_installed = check_ffmpeg_installed()
    ffmpeg_version = get_ffmpeg_version() if ffmpeg_installed else None
    queue_stats = job_queue.get_stats()
    templates = template_service.list_templates()
    temp_stats = get_temp_dir_stats()
    
    return jsonify({
        "status": "online",
        "service": "FFmpeg Video API",
        "version": "2.0.0",
        "auth_enabled": config.AUTH_ENABLED,
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
        },
        "features": {
            "audio_support": True,
            "webhooks": True,
            "template_management": True
        }
    })


# =============================================================================
# Template Endpoints
# =============================================================================

@app.route('/create-template', methods=['POST'])
@require_api_key
def create_template():
    """
    Create a new video template
    ---
    tags:
      - Templates
    security:
      - ApiKeyAuth: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - template_name
            - scenes
          properties:
            template_name:
              type: string
              example: my_custom_template
            description:
              type: string
              example: Custom video template
            scenes:
              type: array
              items:
                type: object
                properties:
                  scene_number:
                    type: integer
                  segments:
                    type: array
                    items:
                      type: object
                      properties:
                        type:
                          type: string
                          enum: [split_top, split_bottom, full_winner, full_screen, image]
                        duration:
                          type: number
                        position:
                          type: string
            output_settings:
              type: object
              properties:
                width:
                  type: integer
                  example: 720
                height:
                  type: integer
                  example: 1280
                fps:
                  type: integer
                  example: 30
    responses:
      201:
        description: Template created successfully
        schema:
          type: object
          properties:
            status:
              type: string
              example: success
            template_id:
              type: string
            template_name:
              type: string
            created_at:
              type: string
      400:
        description: Invalid request
      409:
        description: Template already exists
    """
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
@require_api_key
def list_templates():
    """
    List all available templates
    ---
    tags:
      - Templates
    security:
      - ApiKeyAuth: []
    responses:
      200:
        description: List of templates
        schema:
          type: object
          properties:
            templates:
              type: array
              items:
                type: object
                properties:
                  template_id:
                    type: string
                  template_name:
                    type: string
                  description:
                    type: string
                  scenes_count:
                    type: integer
                  total_duration_seconds:
                    type: number
                  is_default:
                    type: boolean
            count:
              type: integer
    """
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
@require_api_key
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


@app.route('/templates/<template_id>', methods=['PUT'])
@require_api_key
def update_template(template_id):
    """Update an existing template"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response(
                "Request body is required",
                "INVALID_REQUEST"
            )
        
        result = template_service.update_template(template_id, data)
        
        if not result:
            return error_response(
                f"Template not found: {template_id}",
                "TEMPLATE_NOT_FOUND",
                404
            )
        
        logger.info(f"Template updated: {template_id}")
        return jsonify({
            "status": "success",
            "template_id": template_id,
            "message": "Template updated successfully"
        })
        
    except ValueError as e:
        return error_response(str(e), "CANNOT_MODIFY", 403)
    except ValidationError as e:
        return error_response(e.message, e.code, details=e.details)
    except Exception as e:
        logger.error(f"Error updating template: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


@app.route('/templates/<template_id>', methods=['DELETE'])
@require_api_key
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


@app.route('/templates/<template_id>/clone', methods=['POST'])
@require_api_key
def clone_template(template_id):
    """Clone an existing template with a new name"""
    try:
        data = request.get_json() or {}
        new_name = data.get("new_name")
        
        if not new_name:
            return error_response(
                "new_name is required",
                "INVALID_REQUEST"
            )
        
        result = template_service.clone_template(template_id, new_name)
        
        if not result:
            return error_response(
                f"Template not found: {template_id}",
                "TEMPLATE_NOT_FOUND",
                404
            )
        
        logger.info(f"Template cloned: {template_id} -> {new_name}")
        return jsonify(result), 201
        
    except ValueError as e:
        return error_response(str(e), "TEMPLATE_EXISTS", 409)
    except ValidationError as e:
        return error_response(e.message, e.code, details=e.details)
    except Exception as e:
        logger.error(f"Error cloning template: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


@app.route('/templates/validate', methods=['POST'])
@require_api_key
def validate_template():
    """Validate a template structure without saving"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response(
                "Request body is required",
                "INVALID_REQUEST"
            )
        
        # Validate template structure
        validate_template_structure(data)
        
        # Calculate stats
        total_duration = sum(
            segment.get("duration", 0)
            for scene in data.get("scenes", [])
            for segment in scene.get("segments", [])
        )
        
        return jsonify({
            "valid": True,
            "template_name": data.get("template_name"),
            "scenes_count": len(data.get("scenes", [])),
            "total_duration_seconds": total_duration,
            "message": "Template structure is valid"
        })
        
    except ValidationError as e:
        return jsonify({
            "valid": False,
            "error": e.message,
            "code": e.code,
            "details": e.details
        }), 200  # Return 200 since validation endpoint worked
    except Exception as e:
        logger.error(f"Error validating template: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


@app.route('/templates/<template_id>/export', methods=['GET'])
@require_api_key
def export_template(template_id):
    """Export a template as JSON file download"""
    try:
        template = template_service.get_template(template_id)
        
        if not template:
            return error_response(
                f"Template not found: {template_id}",
                "TEMPLATE_NOT_FOUND",
                404
            )
        
        import json
        response = Response(
            json.dumps(template, indent=2),
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename={template_id}.json'
            }
        )
        return response
        
    except Exception as e:
        logger.error(f"Error exporting template: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


@app.route('/templates/import', methods=['POST'])
@require_api_key
def import_template():
    """Import a template from JSON"""
    try:
        data = request.get_json()
        
        if not data:
            return error_response(
                "Request body is required",
                "INVALID_REQUEST"
            )
        
        # Validate and create
        validate_template_structure(data)
        result = template_service.create_template(data)
        
        logger.info(f"Template imported: {result['template_name']}")
        return jsonify(result), 201
        
    except ValidationError as e:
        return error_response(e.message, e.code, details=e.details)
    except ValueError as e:
        return error_response(str(e), "TEMPLATE_EXISTS", 409)
    except Exception as e:
        logger.error(f"Error importing template: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


# =============================================================================
# Video Rendering Endpoints
# =============================================================================

@app.route('/render-video', methods=['POST'])
@require_api_key
def render_video():
    """
    Submit a video rendering job
    ---
    tags:
      - Rendering
    security:
      - ApiKeyAuth: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - template_id
            - images
          properties:
            template_id:
              type: string
              example: fight_video_standard
              description: Template ID or name to use
            images:
              type: object
              description: "Images for each scene (scene_1, scene_2, etc.)"
              example:
                scene_1:
                  split_top: "https://example.com/top.png"
                  split_bottom: "https://example.com/bottom.png"
                  full_winner: "https://example.com/winner.png"
            custom_text:
              type: object
              description: Optional text overlays per scene
              example:
                scene_1: "Round 1"
            audio:
              type: object
              description: Optional audio settings
              properties:
                url:
                  type: string
                  description: HTTPS URL to audio file
                volume:
                  type: number
                  description: "Volume level (0.0 to 2.0)"
                  default: 1.0
                fade_in:
                  type: number
                  description: Fade in duration in seconds
                  default: 0
                fade_out:
                  type: number
                  description: Fade out duration in seconds
                  default: 0
                loop:
                  type: boolean
                  description: Loop audio to match video length
                  default: true
            webhook_url:
              type: string
              description: HTTPS URL to receive completion notification
            render_mode:
              type: string
              enum: [fast, balanced, quality]
              description: "Render speed/quality tradeoff. fast=fastest (default), balanced=good quality, quality=best quality but slow"
              default: fast
    responses:
      202:
        description: Job submitted successfully
        schema:
          type: object
          properties:
            status:
              type: string
              example: processing
            job_id:
              type: string
            template_id:
              type: string
            estimated_time_seconds:
              type: integer
            check_status_url:
              type: string
      400:
        description: Invalid request
      404:
        description: Template not found
      503:
        description: Queue full or FFmpeg unavailable
    """
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
        
        # Validate audio settings if provided
        if "audio" in data:
            validate_audio_settings(data["audio"])
        
        # Validate webhook URL if provided
        webhook_url = data.get("webhook_url")
        if webhook_url:
            validate_webhook_url(webhook_url)
        
        # Validate render mode if provided
        render_mode = data.get("render_mode")
        if render_mode:
            validate_render_mode(render_mode)
        
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
        
        response_data = {
            "status": "processing",
            "job_id": job.job_id,
            "template_id": template_id,
            "estimated_time_seconds": estimated_time,
            "check_status_url": f"/status/{job.job_id}"
        }
        
        if webhook_url:
            response_data["webhook_url"] = webhook_url
            response_data["webhook_note"] = "You will receive a POST when job completes"
        
        return jsonify(response_data), 202
        
    except ValidationError as e:
        return error_response(e.message, e.code, details=e.details)
    except ValueError as e:
        # Queue full
        return error_response(str(e), "QUEUE_FULL", 503)
    except Exception as e:
        logger.error(f"Error submitting render job: {str(e)}")
        return error_response(str(e), "SERVER_ERROR", 500)


@app.route('/status/<job_id>', methods=['GET'])
@require_api_key
def get_job_status(job_id):
    """
    Get status of a rendering job
    ---
    tags:
      - Rendering
    security:
      - ApiKeyAuth: []
    parameters:
      - name: job_id
        in: path
        type: string
        required: true
        description: Job ID returned from render-video
    responses:
      200:
        description: Job status
        schema:
          type: object
          properties:
            job_id:
              type: string
            template_id:
              type: string
            status:
              type: string
              enum: [queued, processing, completed, failed]
            progress:
              type: integer
              description: Progress percentage (0-100)
            created_at:
              type: string
            started_at:
              type: string
            completed_at:
              type: string
            download_url:
              type: string
              description: Available when status is completed
            file_size_mb:
              type: number
            duration_seconds:
              type: number
            error:
              type: object
              description: Available when status is failed
              properties:
                message:
                  type: string
                code:
                  type: string
      404:
        description: Job not found
    """
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
    """
    Download rendered video (PUBLIC - no API key required)
    ---
    tags:
      - Rendering
    security: []
    parameters:
      - name: job_id
        in: path
        type: string
        required: true
        description: Job ID of completed render (acts as access token)
    produces:
      - video/mp4
    responses:
      200:
        description: MP4 video file
      400:
        description: Video not ready
      404:
        description: Job or video not found
    """
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
@require_api_key
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
@require_api_key
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
    logger.info(f"Auth enabled: {config.AUTH_ENABLED}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
