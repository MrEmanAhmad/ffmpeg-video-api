# FFmpeg Video Template API

A Flask-based API service for creating videos from image sequences using FFmpeg. Supports reusable templates, background processing, and easy deployment to Render.com.

## Features

- **Template System**: Define reusable video structures with scenes, durations, and layouts
- **Split-Screen Support**: Create videos with top/bottom split-screen effects
- **Background Processing**: Async video rendering with job status tracking
- **Local Storage**: Videos stored temporarily and accessible via download endpoint
- **Auto-Cleanup**: Old videos automatically cleaned up after 24 hours
- **n8n Compatible**: Simple REST API perfect for workflow automation

## Quick Start

### Prerequisites

- Python 3.11+
- FFmpeg installed and accessible in PATH

### Local Development

1. **Clone and install dependencies:**

```bash
git clone <your-repo-url>
cd ffmpeg-video-api
pip install -r requirements.txt
```

2. **Install FFmpeg:**

```bash
# Windows (with Chocolatey)
choco install ffmpeg

# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg
```

3. **Run the server:**

```bash
python app.py
```

The API will be available at `http://localhost:10000`

4. **Verify it's working:**

```bash
curl http://localhost:10000/
```

## Deployment to Render.com

1. **Push code to GitHub**

2. **Create new Web Service on Render:**
   - Connect your GitHub repository
   - Render will auto-detect the `render.yaml` configuration

3. **Deploy:**
   - Render will automatically install FFmpeg and dependencies
   - Your API will be available at `https://your-service.onrender.com`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `10000` | Server port |
| `MAX_CONCURRENT_JOBS` | `2` | Maximum parallel video renders |
| `MAX_QUEUE_SIZE` | `10` | Maximum pending jobs in queue |
| `VIDEO_RETENTION_HOURS` | `24` | Hours to keep rendered videos |
| `TEMP_DIR` | `/tmp/videos` | Directory for temporary files |
| `IMAGE_DOWNLOAD_TIMEOUT` | `30` | Seconds to wait for image downloads |
| `ALLOWED_DOMAINS` | `` | Comma-separated whitelist (empty = allow all HTTPS) |

## API Endpoints

### Health Check

```
GET /
```

**Response:**
```json
{
  "status": "online",
  "service": "FFmpeg Video API",
  "version": "1.0.0",
  "ffmpeg": {
    "installed": true,
    "version": "ffmpeg version 6.0..."
  },
  "queue": {
    "active_jobs": 1,
    "processing": 1,
    "queued": 0,
    "max_concurrent": 2
  },
  "templates": {
    "count": 1,
    "available": ["fight_video_standard"]
  },
  "storage": {
    "temp_files": 5,
    "temp_size_mb": 45.2
  }
}
```

### Create Template

```
POST /create-template
```

**Request:**
```json
{
  "template_name": "my_custom_template",
  "description": "Custom video template",
  "scenes": [
    {
      "scene_number": 1,
      "segments": [
        {"type": "split_top", "duration": 3, "position": "top_half"},
        {"type": "split_bottom", "duration": 3, "position": "bottom_half"},
        {"type": "full_winner", "duration": 4, "position": "full_screen"}
      ]
    }
  ],
  "output_settings": {
    "width": 720,
    "height": 1280,
    "fps": 30,
    "format": "mp4",
    "codec": "libx264"
  },
  "transitions": {
    "enabled": true,
    "type": "fade",
    "duration": 0.5
  }
}
```

**Response (201):**
```json
{
  "status": "success",
  "template_id": "my_custom_template",
  "template_name": "my_custom_template",
  "created_at": "2026-01-06T12:00:00Z"
}
```

### List Templates

```
GET /templates
```

**Response:**
```json
{
  "templates": [
    {
      "template_id": "fight_video_standard",
      "template_name": "fight_video_standard",
      "description": "8 scenes with split screen and winner reveal",
      "scenes_count": 8,
      "total_duration_seconds": 80,
      "created_at": "2026-01-01T00:00:00Z",
      "is_default": true
    }
  ],
  "count": 1
}
```

### Get Template

```
GET /templates/{template_id}
```

**Response:**
```json
{
  "template_id": "fight_video_standard",
  "template_name": "fight_video_standard",
  "description": "8 scenes with split screen and winner reveal",
  "scenes": [...],
  "output_settings": {...},
  "created_at": "2026-01-01T00:00:00Z"
}
```

### Render Video

```
POST /render-video
```

**Request:**
```json
{
  "template_id": "fight_video_standard",
  "images": {
    "scene_1": {
      "split_top": "https://example.com/image1.png",
      "split_bottom": "https://example.com/image2.png",
      "full_winner": "https://example.com/image3.png"
    },
    "scene_2": {
      "split_top": "https://example.com/image4.png",
      "split_bottom": "https://example.com/image5.png",
      "full_winner": "https://example.com/image6.png"
    }
  },
  "custom_text": {
    "scene_1": "Ape vs Lion",
    "scene_2": "Ape vs Tiger"
  },
  "audio_url": "https://example.com/background-music.mp3"
}
```

**Response (202):**
```json
{
  "status": "processing",
  "job_id": "abc123-def456-ghi789",
  "template_id": "fight_video_standard",
  "estimated_time_seconds": 80,
  "check_status_url": "/status/abc123-def456-ghi789"
}
```

### Check Job Status

```
GET /status/{job_id}
```

**Response (Processing):**
```json
{
  "job_id": "abc123-def456-ghi789",
  "template_id": "fight_video_standard",
  "status": "processing",
  "progress": 45,
  "created_at": "2026-01-06T12:00:00Z",
  "started_at": "2026-01-06T12:00:01Z"
}
```

**Response (Completed):**
```json
{
  "job_id": "abc123-def456-ghi789",
  "template_id": "fight_video_standard",
  "status": "completed",
  "progress": 100,
  "created_at": "2026-01-06T12:00:00Z",
  "started_at": "2026-01-06T12:00:01Z",
  "completed_at": "2026-01-06T12:01:30Z",
  "download_url": "/download/abc123-def456-ghi789",
  "file_size_mb": 12.5,
  "duration_seconds": 80
}
```

**Response (Failed):**
```json
{
  "job_id": "abc123-def456-ghi789",
  "template_id": "fight_video_standard",
  "status": "failed",
  "progress": 30,
  "created_at": "2026-01-06T12:00:00Z",
  "started_at": "2026-01-06T12:00:01Z",
  "completed_at": "2026-01-06T12:00:15Z",
  "error": {
    "message": "Failed to download image: Connection timeout",
    "code": "IMAGE_DOWNLOAD_FAILED"
  }
}
```

### Download Video

```
GET /download/{job_id}
```

Returns the MP4 video file with proper headers for download.

### Cleanup Old Files

```
POST /cleanup?hours=24
```

**Response:**
```json
{
  "status": "success",
  "cleaned_count": 5,
  "cleaned_size_mb": 125.5,
  "jobs_cleaned": 3,
  "errors": []
}
```

### List All Jobs

```
GET /jobs
```

**Response:**
```json
{
  "jobs": [...],
  "stats": {
    "total_jobs": 10,
    "queued": 2,
    "processing": 1,
    "completed": 6,
    "failed": 1,
    "max_workers": 2,
    "max_queue_size": 10
  }
}
```

## Error Responses

All errors follow this format:

```json
{
  "error": true,
  "message": "Description of the error",
  "code": "ERROR_CODE",
  "details": {}
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_REQUEST` | 400 | Missing or invalid request data |
| `INVALID_URL` | 400 | Invalid image URL format |
| `MISSING_IMAGES` | 400 | Required images not provided |
| `TEMPLATE_NOT_FOUND` | 404 | Template does not exist |
| `JOB_NOT_FOUND` | 404 | Job ID not found |
| `VIDEO_NOT_READY` | 400 | Video still processing |
| `VIDEO_NOT_FOUND` | 404 | Video file was cleaned up |
| `TEMPLATE_EXISTS` | 409 | Template name already exists |
| `CANNOT_DELETE` | 403 | Cannot delete default template |
| `QUEUE_FULL` | 503 | Job queue is at capacity |
| `FFMPEG_NOT_AVAILABLE` | 503 | FFmpeg not installed |
| `FFMPEG_ERROR` | 500 | FFmpeg processing failed |
| `IMAGE_DOWNLOAD_FAILED` | 500 | Could not download image |
| `SERVER_ERROR` | 500 | Unexpected server error |

## Default Template: fight_video_standard

The API comes with a default template for creating fight videos:

- **8 scenes**
- **Each scene contains:**
  - Split-screen (top image): 3 seconds
  - Split-screen (bottom image): 3 seconds  
  - Full-screen winner: 4 seconds
- **Total duration:** 80 seconds
- **Output:** 720x1280 @ 30fps MP4

### Using the Default Template

```bash
curl -X POST http://localhost:10000/render-video \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "fight_video_standard",
    "images": {
      "scene_1": {
        "split_top": "https://your-images.com/scene1_top.png",
        "split_bottom": "https://your-images.com/scene1_bottom.png",
        "full_winner": "https://your-images.com/scene1_winner.png"
      },
      "scene_2": {
        "split_top": "https://your-images.com/scene2_top.png",
        "split_bottom": "https://your-images.com/scene2_bottom.png",
        "full_winner": "https://your-images.com/scene2_winner.png"
      }
    }
  }'
```

## n8n Integration Example

### Workflow Steps:

1. **HTTP Request Node** - Submit render job:
   - Method: POST
   - URL: `https://your-api.onrender.com/render-video`
   - Body: JSON with template_id and images

2. **Wait Node** - Wait for estimated time (or poll status)

3. **HTTP Request Node** - Check status:
   - Method: GET
   - URL: `https://your-api.onrender.com/status/{{$json.job_id}}`

4. **IF Node** - Check if status is "completed"

5. **HTTP Request Node** - Download video:
   - Method: GET
   - URL: `https://your-api.onrender.com/download/{{$json.job_id}}`

6. **Google Drive Node** - Upload video to Drive

## Limitations (Free Tier)

- **Videos deleted on restart**: Render free tier doesn't persist storage
- **24-hour retention**: Videos auto-deleted after 24 hours
- **2 concurrent jobs**: Limited parallel processing
- **Cold starts**: First request may be slow after inactivity

## Troubleshooting

### FFmpeg not found

```bash
# Check if FFmpeg is installed
ffmpeg -version

# On Render, FFmpeg is installed via buildCommand in render.yaml
```

### Images failing to download

- Ensure URLs are HTTPS
- Check if domain is in ALLOWED_DOMAINS (if configured)
- Verify images are publicly accessible

### Video rendering fails

- Check job status for error details: `GET /status/{job_id}`
- View server logs on Render dashboard
- Ensure all required images are provided for each scene

### Queue is full

- Wait for current jobs to complete
- Check `/jobs` endpoint for queue status
- Increase `MAX_QUEUE_SIZE` if needed

## Project Structure

```
/
├── app.py                      # Main Flask application
├── config.py                   # Configuration settings
├── requirements.txt            # Python dependencies
├── render.yaml                 # Render deployment config
├── README.md                   # This file
├── templates/                  # JSON template storage
│   └── fight_video_standard.json
├── services/
│   ├── __init__.py
│   ├── template_service.py     # Template CRUD operations
│   ├── video_service.py        # FFmpeg video rendering
│   └── job_queue.py            # Background job processing
└── utils/
    ├── __init__.py
    ├── ffmpeg_builder.py       # FFmpeg command builder
    ├── validators.py           # Input validation
    └── cleanup.py              # File cleanup utilities
```

## License

MIT License

