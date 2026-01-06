"""
Video rendering service using FFmpeg
"""
import os
import logging
import requests
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import config
from utils.ffmpeg_builder import FFmpegBuilder, run_ffmpeg_command
from utils.validators import validate_image_url, ValidationError
from services.job_queue import Job, JobStatus, job_queue

logger = logging.getLogger(__name__)


class VideoServiceError(Exception):
    """Custom error for video service"""
    def __init__(self, message: str, code: str = "VIDEO_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


def send_webhook(webhook_url: str, payload: dict) -> bool:
    """
    Send webhook notification
    
    Args:
        webhook_url: URL to POST to
        payload: JSON payload to send
        
    Returns:
        True if successful, False otherwise
    """
    if not webhook_url:
        return False
    
    for attempt in range(config.WEBHOOK_RETRIES):
        try:
            logger.info(f"Sending webhook to {webhook_url} (attempt {attempt + 1})")
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=config.WEBHOOK_TIMEOUT,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            logger.info(f"Webhook sent successfully: {response.status_code}")
            return True
        except requests.RequestException as e:
            logger.warning(f"Webhook attempt {attempt + 1} failed: {str(e)}")
    
    logger.error(f"All webhook attempts failed for {webhook_url}")
    return False


class VideoService:
    """Service for rendering videos from templates"""
    
    def __init__(self, temp_dir: Path = None):
        self.temp_dir = temp_dir or config.TEMP_DIR
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def download_file(self, url: str, output_path: Path, timeout: int = None, 
                      expected_type: str = None) -> Path:
        """
        Download a file from URL
        
        Args:
            url: File URL
            output_path: Where to save the file
            timeout: Download timeout in seconds
            expected_type: Expected content type prefix (e.g., 'image/', 'audio/')
            
        Returns:
            Path to downloaded file
            
        Raises:
            VideoServiceError: If download fails
        """
        timeout = timeout or config.IMAGE_DOWNLOAD_TIMEOUT
        
        try:
            logger.info(f"Downloading: {url}")
            
            response = requests.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # Check content type if specified
            if expected_type:
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith(expected_type):
                    raise VideoServiceError(
                        f"URL does not return expected type {expected_type}: {content_type}",
                        "INVALID_CONTENT_TYPE"
                    )
            
            # Save to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded to: {output_path}")
            return output_path
            
        except requests.Timeout:
            raise VideoServiceError(
                f"Download timed out after {timeout}s: {url}",
                "DOWNLOAD_TIMEOUT"
            )
        except requests.RequestException as e:
            raise VideoServiceError(
                f"Failed to download: {str(e)}",
                "DOWNLOAD_FAILED"
            )
    
    def download_image(self, url: str, output_path: Path, timeout: int = None) -> Path:
        """
        Download an image from URL
        
        Args:
            url: Image URL
            output_path: Where to save the image
            timeout: Download timeout in seconds
            
        Returns:
            Path to downloaded image
            
        Raises:
            VideoServiceError: If download fails
        """
        try:
            # Validate URL
            validate_image_url(url)
            return self.download_file(url, output_path, timeout, expected_type='image/')
        except ValidationError as e:
            raise VideoServiceError(e.message, e.code)
    
    def download_audio(self, url: str, output_path: Path, timeout: int = None) -> Path:
        """
        Download an audio file from URL
        
        Args:
            url: Audio URL
            output_path: Where to save the audio
            timeout: Download timeout in seconds
            
        Returns:
            Path to downloaded audio
            
        Raises:
            VideoServiceError: If download fails
        """
        # Audio can be various types, so we don't strictly check content-type
        # FFmpeg will validate if it's actually audio
        return self.download_file(url, output_path, timeout)
    
    def download_all_images(self, job: Job, template: dict) -> Dict[str, Dict[str, Path]]:
        """
        Download all images for a render job (PARALLEL for speed)
        
        Args:
            job: The render job
            template: Template configuration
            
        Returns:
            Dictionary mapping scene -> segment_type -> local path
        """
        images_data = job.request_data.get("images", {})
        job_dir = self.temp_dir / job.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # Collect all download tasks
        download_tasks = []
        for scene in template.get("scenes", []):
            scene_num = scene["scene_number"]
            scene_key = f"scene_{scene_num}"
            scene_images = images_data.get(scene_key, {})
            
            for segment in scene.get("segments", []):
                segment_type = segment["type"]
                image_url = scene_images.get(segment_type)
                
                if not image_url:
                    raise VideoServiceError(
                        f"Missing image URL for {scene_key}.{segment_type}",
                        "MISSING_IMAGE"
                    )
                
                # Determine file extension from URL
                parsed = urlparse(image_url)
                ext = Path(parsed.path).suffix or ".png"
                output_path = job_dir / f"{scene_key}_{segment_type}{ext}"
                
                download_tasks.append((scene_key, segment_type, image_url, output_path))
        
        total_images = len(download_tasks)
        downloaded = {}
        downloaded_count = 0
        download_lock = threading.Lock()
        errors = []
        
        def download_task(task: Tuple[str, str, str, Path]) -> Tuple[str, str, Path]:
            """Download a single image and return result"""
            scene_key, segment_type, url, output_path = task
            try:
                self.download_image(url, output_path)
                return (scene_key, segment_type, output_path, None)
            except VideoServiceError as e:
                return (scene_key, segment_type, None, e)
        
        # Execute downloads in parallel
        logger.info(f"Downloading {total_images} images in parallel (max {config.PARALLEL_DOWNLOADS} concurrent)")
        
        with ThreadPoolExecutor(max_workers=config.PARALLEL_DOWNLOADS) as executor:
            futures = {executor.submit(download_task, task): task for task in download_tasks}
            
            for future in as_completed(futures):
                scene_key, segment_type, output_path, error = future.result()
                
                with download_lock:
                    if error:
                        errors.append(error)
                    else:
                        if scene_key not in downloaded:
                            downloaded[scene_key] = {}
                        downloaded[scene_key][segment_type] = output_path
                    
                    # Update progress (downloading is ~20% of work now, faster)
                    downloaded_count += 1
                    progress = int((downloaded_count / total_images) * 20)
                    job_queue.update_job_progress(job.job_id, progress)
        
        # Check for errors
        if errors:
            raise errors[0]  # Raise first error
        
        logger.info(f"All {total_images} images downloaded successfully")
        return downloaded
    
    def render_scene(
        self,
        builder: FFmpegBuilder,
        scene: dict,
        images: Dict[str, Path],
        output_dir: Path,
        scene_number: int,
        custom_text: str = None
    ) -> List[Path]:
        """
        Render a single scene's video segments
        
        Args:
            builder: FFmpegBuilder instance
            scene: Scene configuration from template
            images: Downloaded images for this scene
            output_dir: Directory for output files
            scene_number: Scene number for naming
            custom_text: Optional text overlay
            
        Returns:
            List of rendered segment video paths
        """
        segment_videos = []
        
        for i, segment in enumerate(scene.get("segments", [])):
            segment_type = segment["type"]
            duration = segment.get("duration", 3)
            
            output_path = output_dir / f"scene{scene_number}_segment{i}_{segment_type}.mp4"
            
            if segment_type in ("split_top", "split_bottom"):
                # For split screen, we need both top and bottom images
                # Check if this is the first split segment and next is also split
                if segment_type == "split_top":
                    top_image = images.get("split_top")
                    bottom_image = images.get("split_bottom")
                    
                    if not top_image or not bottom_image:
                        raise VideoServiceError(
                            f"Missing split screen images for scene {scene_number}",
                            "MISSING_IMAGE"
                        )
                    
                    cmd = builder.build_split_screen_command(
                        top_image=top_image,
                        bottom_image=bottom_image,
                        output_path=output_path,
                        duration=duration
                    )
                    
                    result = run_ffmpeg_command(cmd)
                    if not result["success"]:
                        raise VideoServiceError(
                            f"FFmpeg error: {result['error']}",
                            "FFMPEG_ERROR"
                        )
                    
                    segment_videos.append(output_path)
                
                # Skip split_bottom as it's handled with split_top
                elif segment_type == "split_bottom":
                    continue
                    
            elif segment_type in ("full_winner", "full_screen", "full"):
                # Full screen image
                image_path = images.get(segment_type) or images.get("full_winner") or images.get("full")
                
                if not image_path:
                    raise VideoServiceError(
                        f"Missing full screen image for scene {scene_number}",
                        "MISSING_IMAGE"
                    )
                
                cmd = builder.build_full_screen_command(
                    image=image_path,
                    output_path=output_path,
                    duration=duration,
                    text_overlay=custom_text
                )
                
                result = run_ffmpeg_command(cmd)
                if not result["success"]:
                    raise VideoServiceError(
                        f"FFmpeg error: {result['error']}",
                        "FFMPEG_ERROR"
                    )
                
                segment_videos.append(output_path)
            
            else:
                # Generic full screen for unknown types
                image_path = images.get(segment_type)
                
                if image_path:
                    cmd = builder.build_full_screen_command(
                        image=image_path,
                        output_path=output_path,
                        duration=duration,
                        text_overlay=custom_text
                    )
                    
                    result = run_ffmpeg_command(cmd)
                    if not result["success"]:
                        raise VideoServiceError(
                            f"FFmpeg error: {result['error']}",
                            "FFMPEG_ERROR"
                        )
                    
                    segment_videos.append(output_path)
        
        return segment_videos
    
    def render_video(self, job: Job, template: dict) -> Path:
        """
        Render complete video from template and images (PARALLEL for speed)
        
        Args:
            job: The render job
            template: Template configuration
            
        Returns:
            Path to final rendered video
        """
        job_dir = self.temp_dir / job.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # Apply render mode if specified
        render_mode = job.request_data.get("render_mode", "fast")
        output_settings = template.get("output_settings", {}).copy()
        
        # Merge with default settings
        for key, value in config.DEFAULT_OUTPUT_SETTINGS.items():
            if key not in output_settings:
                output_settings[key] = value
        
        # Apply render mode presets
        if render_mode in config.RENDER_MODES:
            mode_settings = config.RENDER_MODES[render_mode]
            output_settings.update(mode_settings)
            logger.info(f"Using render mode: {render_mode}")
        
        builder = FFmpegBuilder(output_settings)
        
        # Download all images (parallel)
        logger.info(f"Downloading images for job {job.job_id}")
        downloaded_images = self.download_all_images(job, template)
        
        # Prepare scene rendering tasks
        scenes = template.get("scenes", [])
        custom_texts = job.request_data.get("custom_text", {})
        
        # Results storage with ordering
        scene_results = {}
        render_lock = threading.Lock()
        completed_scenes = [0]  # Use list for mutable counter in closure
        errors = []
        
        def render_scene_task(scene: dict) -> Tuple[int, List[Path], Optional[Exception]]:
            """Render a single scene and return results"""
            scene_num = scene["scene_number"]
            scene_key = f"scene_{scene_num}"
            
            try:
                logger.info(f"Rendering scene {scene_num} for job {job.job_id}")
                
                scene_videos = self.render_scene(
                    builder=builder,
                    scene=scene,
                    images=downloaded_images[scene_key],
                    output_dir=job_dir,
                    scene_number=scene_num,
                    custom_text=custom_texts.get(scene_key)
                )
                
                return (scene_num, scene_videos, None)
            except Exception as e:
                return (scene_num, [], e)
        
        # Render scenes in parallel
        max_parallel = min(config.PARALLEL_SCENES, len(scenes))
        logger.info(f"Rendering {len(scenes)} scenes in parallel (max {max_parallel} concurrent)")
        
        with ThreadPoolExecutor(max_workers=max_parallel) as executor:
            futures = {executor.submit(render_scene_task, scene): scene["scene_number"] for scene in scenes}
            
            for future in as_completed(futures):
                scene_num, scene_videos, error = future.result()
                
                with render_lock:
                    if error:
                        errors.append(error)
                    else:
                        scene_results[scene_num] = scene_videos
                    
                    # Update progress (rendering is 20-75% of work)
                    completed_scenes[0] += 1
                    progress = 20 + int((completed_scenes[0] / len(scenes)) * 55)
                    job_queue.update_job_progress(job.job_id, progress)
        
        # Check for errors
        if errors:
            if isinstance(errors[0], VideoServiceError):
                raise errors[0]
            raise VideoServiceError(str(errors[0]), "RENDER_ERROR")
        
        # Collect segment videos in correct order
        all_segment_videos = []
        for scene_num in sorted(scene_results.keys()):
            all_segment_videos.extend(scene_results[scene_num])
        
        logger.info(f"All {len(scenes)} scenes rendered successfully")
        
        # Calculate total duration
        total_duration = sum(
            segment.get("duration", 0)
            for scene in template.get("scenes", [])
            for segment in scene.get("segments", [])
        )
        
        # Check if we have audio to add
        audio_data = job.request_data.get("audio", {})
        audio_url = audio_data.get("url") if isinstance(audio_data, dict) else job.request_data.get("audio_url")
        audio_path = None
        
        # Download audio in parallel with concat preparation
        if audio_url:
            logger.info(f"Downloading audio for job {job.job_id}")
            parsed = urlparse(audio_url)
            audio_ext = Path(parsed.path).suffix or ".mp3"
            audio_path = job_dir / f"audio{audio_ext}"
            
            try:
                self.download_audio(audio_url, audio_path)
            except VideoServiceError as e:
                logger.warning(f"Failed to download audio: {e.message}")
                audio_path = None
        
        # Concatenate all segments
        logger.info(f"Concatenating {len(all_segment_videos)} segments for job {job.job_id}")
        final_output = job_dir / f"final_{job.job_id}.mp4"
        
        # Use combined concat + audio if audio is available
        if audio_path and audio_path.exists():
            # Get audio settings
            volume = audio_data.get("volume", 1.0) if isinstance(audio_data, dict) else 1.0
            fade_in = audio_data.get("fade_in", 0) if isinstance(audio_data, dict) else 0
            fade_out = audio_data.get("fade_out", 0) if isinstance(audio_data, dict) else 0
            loop = audio_data.get("loop", True) if isinstance(audio_data, dict) else True
            
            # Combined concat + audio command
            cmd, concat_file = builder.build_concat_with_audio_command(
                input_files=all_segment_videos,
                audio_path=audio_path,
                output_path=final_output,
                video_duration=total_duration,
                volume=volume,
                fade_in=fade_in,
                fade_out=fade_out,
                loop_audio=loop
            )
            
            result = run_ffmpeg_command(cmd)
            if not result["success"]:
                raise VideoServiceError(
                    f"FFmpeg concat+audio error: {result['error']}",
                    "FFMPEG_ERROR"
                )
            logger.info(f"Video with audio created for job {job.job_id}")
        else:
            # Simple concat without audio
            cmd, concat_file = builder.build_concat_command(
                input_files=all_segment_videos,
                output_path=final_output
            )
            
            result = run_ffmpeg_command(cmd)
            if not result["success"]:
                raise VideoServiceError(
                    f"FFmpeg concat error: {result['error']}",
                    "FFMPEG_ERROR"
                )
        
        job_queue.update_job_progress(job.job_id, 95)
        
        # Clean up intermediate files
        self.cleanup_intermediate_files(job_dir, final_output)
        
        job_queue.update_job_progress(job.job_id, 100)
        
        logger.info(f"Video rendering complete for job {job.job_id}: {final_output}")
        return final_output
    
    def cleanup_intermediate_files(self, job_dir: Path, keep_file: Path):
        """
        Clean up intermediate files after rendering
        
        Args:
            job_dir: Job directory
            keep_file: File to keep (final output)
        """
        try:
            for file_path in job_dir.glob("*"):
                if file_path != keep_file and file_path.is_file():
                    file_path.unlink()
                    logger.debug(f"Deleted intermediate file: {file_path}")
        except Exception as e:
            logger.warning(f"Error cleaning up intermediate files: {e}")
    
    def get_video_path(self, job_id: str) -> Optional[Path]:
        """
        Get path to rendered video for a job
        
        Args:
            job_id: Job ID
            
        Returns:
            Path to video file or None if not found
        """
        job_dir = self.temp_dir / job_id
        final_video = job_dir / f"final_{job_id}.mp4"
        
        if final_video.exists():
            return final_video
        
        return None
    
    def get_video_info(self, video_path: Path) -> dict:
        """
        Get information about a video file
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary with video info
        """
        if not video_path.exists():
            return {}
        
        stat = video_path.stat()
        
        return {
            "file_size_bytes": stat.st_size,
            "file_size_mb": round(stat.st_size / (1024 * 1024), 2),
            "path": str(video_path)
        }


def process_render_job(job: Job):
    """
    Process a video render job (called by job queue)
    
    Args:
        job: Job to process
    """
    from services.template_service import template_service
    
    webhook_url = job.request_data.get("webhook_url")
    
    try:
        # Get template
        template = template_service.get_template(job.template_id)
        if not template:
            raise VideoServiceError(
                f"Template not found: {job.template_id}",
                "TEMPLATE_NOT_FOUND"
            )
        
        # Render video
        video_service = VideoService()
        output_path = video_service.render_video(job, template)
        
        # Get video info
        video_info = video_service.get_video_info(output_path)
        
        # Calculate total duration from template
        total_duration = sum(
            segment.get("duration", 0)
            for scene in template.get("scenes", [])
            for segment in scene.get("segments", [])
        )
        
        # Mark job as completed
        job_queue.mark_job_completed(
            job.job_id,
            output_path=str(output_path),
            file_size_bytes=video_info.get("file_size_bytes"),
            duration_seconds=total_duration
        )
        
        # Send webhook notification
        if webhook_url:
            send_webhook(webhook_url, {
                "event": "job_completed",
                "job_id": job.job_id,
                "status": "completed",
                "template_id": job.template_id,
                "download_url": f"/download/{job.job_id}",
                "file_size_mb": video_info.get("file_size_mb"),
                "duration_seconds": total_duration
            })
        
    except VideoServiceError as e:
        logger.error(f"Video service error for job {job.job_id}: {e.message}")
        job_queue.mark_job_failed(job.job_id, e.message, e.code)
        
        # Send failure webhook
        if webhook_url:
            send_webhook(webhook_url, {
                "event": "job_failed",
                "job_id": job.job_id,
                "status": "failed",
                "template_id": job.template_id,
                "error": {
                    "message": e.message,
                    "code": e.code
                }
            })
        
    except Exception as e:
        logger.error(f"Unexpected error for job {job.job_id}: {str(e)}")
        job_queue.mark_job_failed(job.job_id, str(e), "UNEXPECTED_ERROR")
        
        # Send failure webhook
        if webhook_url:
            send_webhook(webhook_url, {
                "event": "job_failed",
                "job_id": job.job_id,
                "status": "failed",
                "template_id": job.template_id,
                "error": {
                    "message": str(e),
                    "code": "UNEXPECTED_ERROR"
                }
            })


# Set the job processor
job_queue.set_processor(process_render_job)

# Global video service instance
video_service = VideoService()
