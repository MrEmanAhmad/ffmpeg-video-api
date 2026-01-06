"""
Input validation utilities for FFmpeg Video API
"""
import re
from urllib.parse import urlparse
from typing import Optional, List
import config


class ValidationError(Exception):
    """Custom validation error with error code"""
    def __init__(self, message: str, code: str = "INVALID_REQUEST", details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


def validate_image_url(url: str, allowed_domains: List[str] = None) -> str:
    """
    Validate image URL for security
    
    Args:
        url: The URL to validate
        allowed_domains: Optional list of allowed domains
        
    Returns:
        The validated URL
        
    Raises:
        ValidationError: If URL is invalid
    """
    if not url:
        raise ValidationError("Image URL is required", "INVALID_URL")
    
    # Must be HTTPS
    if not url.startswith("https://"):
        raise ValidationError(
            "Only HTTPS URLs are allowed",
            "INVALID_URL",
            {"url": url}
        )
    
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValidationError(
            "Invalid URL format",
            "INVALID_URL",
            {"url": url}
        )
    
    # Check domain whitelist if configured
    domains = allowed_domains or config.ALLOWED_DOMAINS
    if domains:
        if parsed.netloc not in domains:
            raise ValidationError(
                f"Domain not allowed: {parsed.netloc}",
                "DOMAIN_NOT_ALLOWED",
                {"url": url, "domain": parsed.netloc, "allowed": domains}
            )
    
    return url


def validate_template_name(name: str) -> str:
    """
    Validate template name for safe file storage
    
    Args:
        name: Template name to validate
        
    Returns:
        Sanitized template name
        
    Raises:
        ValidationError: If name is invalid
    """
    if not name:
        raise ValidationError("Template name is required", "INVALID_TEMPLATE_NAME")
    
    # Only allow alphanumeric, underscore, hyphen
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise ValidationError(
            "Template name can only contain letters, numbers, underscores, and hyphens",
            "INVALID_TEMPLATE_NAME",
            {"name": name}
        )
    
    # Limit length
    if len(name) > 100:
        raise ValidationError(
            "Template name must be 100 characters or less",
            "INVALID_TEMPLATE_NAME",
            {"name": name, "length": len(name)}
        )
    
    return name


def validate_template_structure(template_data: dict) -> dict:
    """
    Validate template structure
    
    Args:
        template_data: Template data to validate
        
    Returns:
        Validated template data
        
    Raises:
        ValidationError: If structure is invalid
    """
    required_fields = ["template_name", "scenes"]
    
    for field in required_fields:
        if field not in template_data:
            raise ValidationError(
                f"Missing required field: {field}",
                "INVALID_TEMPLATE",
                {"missing_field": field}
            )
    
    # Validate template name
    validate_template_name(template_data["template_name"])
    
    # Validate scenes
    scenes = template_data.get("scenes", [])
    if not scenes:
        raise ValidationError(
            "Template must have at least one scene",
            "INVALID_TEMPLATE",
            {"scenes_count": 0}
        )
    
    for i, scene in enumerate(scenes):
        if "scene_number" not in scene:
            raise ValidationError(
                f"Scene {i+1} missing scene_number",
                "INVALID_TEMPLATE",
                {"scene_index": i}
            )
        
        if "segments" not in scene or not scene["segments"]:
            raise ValidationError(
                f"Scene {scene.get('scene_number', i+1)} must have at least one segment",
                "INVALID_TEMPLATE",
                {"scene_number": scene.get("scene_number", i+1)}
            )
        
        for j, segment in enumerate(scene["segments"]):
            if "type" not in segment:
                raise ValidationError(
                    f"Segment {j+1} in scene {scene.get('scene_number', i+1)} missing type",
                    "INVALID_TEMPLATE"
                )
            if "duration" not in segment:
                raise ValidationError(
                    f"Segment {j+1} in scene {scene.get('scene_number', i+1)} missing duration",
                    "INVALID_TEMPLATE"
                )
    
    # Validate output settings if provided
    if "output_settings" in template_data:
        settings = template_data["output_settings"]
        if "width" in settings and (settings["width"] < 100 or settings["width"] > 4096):
            raise ValidationError("Width must be between 100 and 4096", "INVALID_OUTPUT_SETTINGS")
        if "height" in settings and (settings["height"] < 100 or settings["height"] > 4096):
            raise ValidationError("Height must be between 100 and 4096", "INVALID_OUTPUT_SETTINGS")
        if "fps" in settings and (settings["fps"] < 1 or settings["fps"] > 120):
            raise ValidationError("FPS must be between 1 and 120", "INVALID_OUTPUT_SETTINGS")
    
    return template_data


def validate_render_request(request_data: dict, template: dict) -> dict:
    """
    Validate render video request against template
    
    Args:
        request_data: Request data to validate
        template: Template to validate against
        
    Returns:
        Validated request data
        
    Raises:
        ValidationError: If request is invalid
    """
    if "images" not in request_data:
        raise ValidationError(
            "Missing required field: images",
            "INVALID_REQUEST"
        )
    
    images = request_data["images"]
    
    # Validate that all required images are provided
    for scene in template.get("scenes", []):
        scene_key = f"scene_{scene['scene_number']}"
        
        if scene_key not in images:
            raise ValidationError(
                f"Missing images for {scene_key}",
                "MISSING_IMAGES",
                {"scene": scene_key}
            )
        
        scene_images = images[scene_key]
        
        for segment in scene.get("segments", []):
            segment_type = segment["type"]
            
            if segment_type not in scene_images:
                raise ValidationError(
                    f"Missing image for {scene_key}.{segment_type}",
                    "MISSING_IMAGES",
                    {"scene": scene_key, "segment_type": segment_type}
                )
            
            # Validate each image URL
            validate_image_url(scene_images[segment_type])
    
    return request_data

