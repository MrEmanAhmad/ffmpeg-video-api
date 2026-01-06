"""
Template management service for FFmpeg Video API
"""
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
import config
from utils.validators import validate_template_name, validate_template_structure

logger = logging.getLogger(__name__)


# Default fight video template with 8 scenes
DEFAULT_FIGHT_VIDEO_TEMPLATE = {
    "template_id": "fight_video_standard",
    "template_name": "fight_video_standard",
    "description": "8 scenes with split screen and winner reveal - standard fight video format",
    "scenes": [
        {
            "scene_number": i,
            "segments": [
                {"type": "split_top", "duration": 3, "position": "top_half"},
                {"type": "split_bottom", "duration": 3, "position": "bottom_half"},
                {"type": "full_winner", "duration": 4, "position": "full_screen"}
            ]
        }
        for i in range(1, 9)  # 8 scenes
    ],
    "output_settings": {
        "width": 720,
        "height": 1280,
        "fps": 30,
        "format": "mp4",
        "codec": "libx264"
    },
    "audio": {
        "enabled": False,
        "source_url": None
    },
    "transitions": {
        "enabled": True,
        "type": "fade",
        "duration": 0.5
    },
    "created_at": "2026-01-01T00:00:00Z",
    "is_default": True
}


class TemplateService:
    """Service for managing video templates"""
    
    def __init__(self, templates_dir: Path = None):
        self.templates_dir = templates_dir or config.TEMPLATES_DIR
        self.templates_dir.mkdir(exist_ok=True)
        self._ensure_default_template()
    
    def _ensure_default_template(self):
        """Ensure the default template exists"""
        default_path = self.templates_dir / "fight_video_standard.json"
        if not default_path.exists():
            self._save_template_file(DEFAULT_FIGHT_VIDEO_TEMPLATE)
            logger.info("Created default fight_video_standard template")
    
    def _get_template_path(self, template_id: str) -> Path:
        """Get the file path for a template"""
        # Sanitize template_id to prevent path traversal
        safe_id = validate_template_name(template_id)
        return self.templates_dir / f"{safe_id}.json"
    
    def _save_template_file(self, template: dict) -> Path:
        """Save template to JSON file"""
        template_id = template.get("template_id") or template.get("template_name")
        file_path = self._get_template_path(template_id)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2)
        
        logger.info(f"Saved template: {template_id}")
        return file_path
    
    def _load_template_file(self, template_id: str) -> Optional[dict]:
        """Load template from JSON file"""
        file_path = self._get_template_path(template_id)
        
        if not file_path.exists():
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def create_template(self, template_data: dict) -> dict:
        """
        Create a new template
        
        Args:
            template_data: Template configuration
            
        Returns:
            Created template with ID and timestamps
        """
        # Validate template structure
        validate_template_structure(template_data)
        
        template_name = template_data["template_name"]
        
        # Check if template already exists
        if self._load_template_file(template_name):
            raise ValueError(f"Template already exists: {template_name}")
        
        # Generate template ID and timestamps
        template_id = template_data.get("template_id") or template_name
        now = datetime.utcnow().isoformat() + "Z"
        
        # Build complete template
        template = {
            "template_id": template_id,
            "template_name": template_name,
            "description": template_data.get("description", ""),
            "scenes": template_data["scenes"],
            "output_settings": {
                **config.DEFAULT_OUTPUT_SETTINGS,
                **template_data.get("output_settings", {})
            },
            "audio": template_data.get("audio", {"enabled": False, "source_url": None}),
            "transitions": template_data.get("transitions", {"enabled": False, "type": "none", "duration": 0}),
            "created_at": now,
            "updated_at": now,
            "is_default": False
        }
        
        # Save to file
        self._save_template_file(template)
        
        return {
            "status": "success",
            "template_id": template_id,
            "template_name": template_name,
            "created_at": now
        }
    
    def get_template(self, template_id: str) -> Optional[dict]:
        """
        Get a template by ID or name
        
        Args:
            template_id: Template ID or name
            
        Returns:
            Template data or None if not found
        """
        return self._load_template_file(template_id)
    
    def list_templates(self) -> List[dict]:
        """
        List all available templates
        
        Returns:
            List of template summaries
        """
        templates = []
        
        for file_path in self.templates_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    template = json.load(f)
                    
                # Calculate total duration
                total_duration = 0
                for scene in template.get("scenes", []):
                    for segment in scene.get("segments", []):
                        total_duration += segment.get("duration", 0)
                
                templates.append({
                    "template_id": template.get("template_id"),
                    "template_name": template.get("template_name"),
                    "description": template.get("description", ""),
                    "scenes_count": len(template.get("scenes", [])),
                    "total_duration_seconds": total_duration,
                    "created_at": template.get("created_at"),
                    "is_default": template.get("is_default", False)
                })
            except Exception as e:
                logger.error(f"Error loading template {file_path}: {e}")
        
        # Sort by name, with default templates first
        templates.sort(key=lambda t: (not t.get("is_default", False), t.get("template_name", "")))
        
        return templates
    
    def delete_template(self, template_id: str) -> bool:
        """
        Delete a template
        
        Args:
            template_id: Template ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        template = self._load_template_file(template_id)
        
        if not template:
            return False
        
        # Don't allow deleting default templates
        if template.get("is_default"):
            raise ValueError("Cannot delete default templates")
        
        file_path = self._get_template_path(template_id)
        file_path.unlink()
        logger.info(f"Deleted template: {template_id}")
        
        return True
    
    def update_template(self, template_id: str, updates: dict) -> Optional[dict]:
        """
        Update an existing template
        
        Args:
            template_id: Template ID to update
            updates: Fields to update
            
        Returns:
            Updated template or None if not found
        """
        template = self._load_template_file(template_id)
        
        if not template:
            return None
        
        # Don't allow updating default templates
        if template.get("is_default"):
            raise ValueError("Cannot modify default templates")
        
        # Update allowed fields
        allowed_updates = ["description", "scenes", "output_settings", "audio", "transitions"]
        
        for field in allowed_updates:
            if field in updates:
                template[field] = updates[field]
        
        template["updated_at"] = datetime.utcnow().isoformat() + "Z"
        
        # Validate updated template
        validate_template_structure(template)
        
        # Save changes
        self._save_template_file(template)
        
        return template
    
    def clone_template(self, template_id: str, new_name: str) -> Optional[dict]:
        """
        Clone an existing template with a new name
        
        Args:
            template_id: Template ID to clone
            new_name: Name for the new template
            
        Returns:
            Created template info or None if source not found
        """
        # Load source template
        source = self._load_template_file(template_id)
        
        if not source:
            return None
        
        # Check if new name already exists
        if self._load_template_file(new_name):
            raise ValueError(f"Template already exists: {new_name}")
        
        # Validate new name
        validate_template_name(new_name)
        
        # Create clone
        now = datetime.utcnow().isoformat() + "Z"
        
        clone = {
            **source,
            "template_id": new_name,
            "template_name": new_name,
            "description": f"Clone of {template_id}: {source.get('description', '')}",
            "created_at": now,
            "updated_at": now,
            "is_default": False,
            "cloned_from": template_id
        }
        
        # Save clone
        self._save_template_file(clone)
        
        return {
            "status": "success",
            "template_id": new_name,
            "template_name": new_name,
            "cloned_from": template_id,
            "created_at": now
        }


# Global template service instance
template_service = TemplateService()

