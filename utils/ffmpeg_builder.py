"""
FFmpeg command builder utilities for video creation
"""
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Optional
import config

logger = logging.getLogger(__name__)


def check_ffmpeg_installed() -> bool:
    """Check if FFmpeg is installed and accessible"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def get_ffmpeg_version() -> Optional[str]:
    """Get FFmpeg version string"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # First line contains version info
            return result.stdout.split('\n')[0]
        return None
    except Exception:
        return None


class FFmpegBuilder:
    """Builder for FFmpeg commands"""
    
    def __init__(self, output_settings: dict = None):
        """
        Initialize FFmpeg builder
        
        Args:
            output_settings: Video output settings (width, height, fps, codec)
        """
        self.settings = {
            **config.DEFAULT_OUTPUT_SETTINGS,
            **(output_settings or {})
        }
        self.width = self.settings["width"]
        self.height = self.settings["height"]
        self.fps = self.settings["fps"]
        self.codec = self.settings.get("codec", "libx264")
    
    def build_split_screen_command(
        self,
        top_image: Path,
        bottom_image: Path,
        output_path: Path,
        duration: float = 3.0
    ) -> List[str]:
        """
        Build FFmpeg command for split-screen video (top + bottom)
        
        Args:
            top_image: Path to top half image
            bottom_image: Path to bottom half image
            output_path: Output video path
            duration: Duration in seconds
            
        Returns:
            FFmpeg command as list of arguments
        """
        half_height = self.height // 2
        
        # Filter complex to scale and stack images vertically
        filter_complex = (
            f"[0:v]scale={self.width}:{half_height}:force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{half_height}:(ow-iw)/2:(oh-ih)/2[top];"
            f"[1:v]scale={self.width}:{half_height}:force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{half_height}:(ow-iw)/2:(oh-ih)/2[bottom];"
            f"[top][bottom]vstack=inputs=2[out]"
        )
        
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(duration), "-i", str(top_image),
            "-loop", "1", "-t", str(duration), "-i", str(bottom_image),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-t", str(duration),
            "-c:v", self.codec,
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            str(output_path)
        ]
        
        return cmd
    
    def build_full_screen_command(
        self,
        image: Path,
        output_path: Path,
        duration: float = 4.0,
        text_overlay: str = None
    ) -> List[str]:
        """
        Build FFmpeg command for full-screen video from image
        
        Args:
            image: Path to image file
            output_path: Output video path
            duration: Duration in seconds
            text_overlay: Optional text to overlay
            
        Returns:
            FFmpeg command as list of arguments
        """
        # Build video filter
        vf_parts = [
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease",
            f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2"
        ]
        
        # Add text overlay if provided
        if text_overlay:
            # Escape special characters for FFmpeg
            escaped_text = text_overlay.replace("'", "'\\''").replace(":", "\\:")
            vf_parts.append(
                f"drawtext=text='{escaped_text}':"
                f"fontsize=60:fontcolor=white:"
                f"x=(w-text_w)/2:y=h-100:"
                f"borderw=3:bordercolor=black"
            )
        
        vf = ",".join(vf_parts)
        
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(duration), "-i", str(image),
            "-vf", vf,
            "-t", str(duration),
            "-c:v", self.codec,
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            str(output_path)
        ]
        
        return cmd
    
    def build_concat_command(
        self,
        input_files: List[Path],
        output_path: Path,
        concat_file: Path = None
    ) -> tuple:
        """
        Build FFmpeg command to concatenate video files
        
        Args:
            input_files: List of video file paths to concatenate
            output_path: Output video path
            concat_file: Path for concat list file (auto-generated if None)
            
        Returns:
            Tuple of (command list, concat file path)
        """
        # Create concat file
        if concat_file is None:
            concat_file = output_path.parent / "concat.txt"
        
        # Write concat file
        with open(concat_file, 'w') as f:
            for input_file in input_files:
                f.write(f"file '{input_file.absolute()}'\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path)
        ]
        
        return cmd, concat_file
    
    def build_concat_with_transitions_command(
        self,
        input_files: List[Path],
        output_path: Path,
        transition_duration: float = 0.5
    ) -> List[str]:
        """
        Build FFmpeg command to concatenate videos with fade transitions
        
        Args:
            input_files: List of video file paths
            output_path: Output video path
            transition_duration: Fade duration in seconds
            
        Returns:
            FFmpeg command as list of arguments
        """
        if len(input_files) < 2:
            # No transitions needed for single file
            cmd, _ = self.build_concat_command(input_files, output_path)
            return cmd
        
        # Build input arguments
        inputs = []
        for f in input_files:
            inputs.extend(["-i", str(f)])
        
        # Build complex filter for xfade transitions
        n = len(input_files)
        filter_parts = []
        
        # For simplicity, use concat without xfade for now
        # xfade requires precise timing calculations
        # This can be enhanced later
        
        # Simple concat approach
        filter_complex = "".join([f"[{i}:v]" for i in range(n)]) + f"concat=n={n}:v=1:a=0[outv]"
        
        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-c:v", self.codec,
            "-pix_fmt", "yuv420p",
            str(output_path)
        ]
        
        return cmd
    
    def build_add_audio_command(
        self,
        video_path: Path,
        audio_url: str,
        output_path: Path,
        loop_audio: bool = True
    ) -> List[str]:
        """
        Build FFmpeg command to add audio to video
        
        Args:
            video_path: Path to video file
            audio_url: URL or path to audio file
            output_path: Output video path
            loop_audio: Whether to loop audio to match video length
            
        Returns:
            FFmpeg command as list of arguments
        """
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", audio_url,
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",  # End when shortest stream ends
            str(output_path)
        ]
        
        return cmd


def run_ffmpeg_command(cmd: List[str], timeout: int = 300) -> dict:
    """
    Execute an FFmpeg command
    
    Args:
        cmd: FFmpeg command as list of arguments
        timeout: Timeout in seconds
        
    Returns:
        Dictionary with success status and output/error
    """
    logger.info(f"Running FFmpeg: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            logger.info("FFmpeg command completed successfully")
            return {
                "success": True,
                "output": result.stdout,
                "error": None
            }
        else:
            logger.error(f"FFmpeg error: {result.stderr}")
            return {
                "success": False,
                "output": result.stdout,
                "error": result.stderr
            }
            
    except subprocess.TimeoutExpired:
        logger.error(f"FFmpeg timeout after {timeout}s")
        return {
            "success": False,
            "output": None,
            "error": f"FFmpeg process timed out after {timeout} seconds"
        }
    except Exception as e:
        logger.error(f"FFmpeg execution error: {str(e)}")
        return {
            "success": False,
            "output": None,
            "error": str(e)
        }

