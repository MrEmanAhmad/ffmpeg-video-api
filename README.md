# FFmpeg Video Template API

A Flask-based API service for creating videos from image sequences using FFmpeg. Supports reusable templates, background processing, audio with effects, webhook notifications, and easy deployment to Render.com.

## Features

- **Template System**: Define reusable video structures with scenes, durations, and layouts
- **Split-Screen Support**: Create videos with top/bottom split-screen effects
- **Audio Support**: Add background music with volume control, fade in/out, and looping
- **Webhook Notifications**: Get notified when jobs complete or fail
- **API Key Authentication**: Secure your API with simple key-based auth
- **Background Processing**: Async video rendering with job status tracking
- **Swagger Documentation**: Interactive API docs at `/docs`
- **Local Storage**: Videos stored temporarily and accessible via download endpoint
- **Auto-Cleanup**: Old videos automatically cleaned up after 24 hours

## Quick Start

### Prerequisites

- Python 3.11+
- FFmpeg installed and accessible in PATH

### Local Development

1. **Clone and install dependencies:**

```bash
git clone https://github.com/MrEmanAhmad/ffmpeg-video-api.git
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

4. **View API Documentation:**

Open `http://localhost:10000/docs` for interactive Swagger documentation.

## Deployment to Render.com

1. **Push code to GitHub**

2. **Create new Web Service on Render:**
   - Connect your GitHub repository
   - Render will auto-detect the `render.yaml` configuration

3. **Set Environment Variables (optional):**
   - `API_KEYS`: Comma-separated list of valid API keys
   - See full list below

4. **Deploy:**
   - Your API will be available at `https://your-service.onrender.com`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `10000` | Server port |
| `API_KEYS` | `` | Comma-separated API keys (empty = no auth) |
| `MAX_CONCURRENT_JOBS` | `2` | Maximum parallel video renders |
| `MAX_QUEUE_SIZE` | `10` | Maximum pending jobs in queue |
| `VIDEO_RETENTION_HOURS` | `24` | Hours to keep rendered videos |
| `TEMP_DIR` | `/tmp/videos` | Directory for temporary files |
| `IMAGE_DOWNLOAD_TIMEOUT` | `30` | Seconds to wait for image downloads |
| `WEBHOOK_TIMEOUT` | `10` | Seconds to wait for webhook response |
| `WEBHOOK_RETRIES` | `3` | Number of webhook retry attempts |
| `ALLOWED_DOMAINS` | `` | Comma-separated image URL whitelist |

## API Authentication

When `API_KEYS` environment variable is set, all endpoints (except `/` and `/docs`) require authentication.

**Add the API key to your request header:**
```
X-API-Key: your-api-key-here
```

## API Endpoints

### Interactive Documentation

Visit `/docs` for Swagger UI with all endpoints, schemas, and try-it-out functionality.

---

### Health Check

```
GET /
```

**Response:**
```json
{
  "status": "online",
  "service": "FFmpeg Video API",
  "version": "2.0.0",
  "auth_enabled": true,
  "ffmpeg": {
    "installed": true,
    "version": "ffmpeg version 5.1.7..."
  },
  "queue": {
    "active_jobs": 1,
    "processing": 1,
    "queued": 0,
    "max_concurrent": 2
  },
  "templates": {
    "count": 4,
    "available": ["fight_video_standard", "fight_video_4_scenes", "slideshow_simple", "comparison_video"]
  },
  "features": {
    "audio_support": true,
    "webhooks": true,
    "template_management": true
  }
}
```

---

### Templates

#### List Templates
```
GET /templates
```

#### Get Template
```
GET /templates/{template_id}
```

#### Create Template
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
    "fps": 30
  }
}
```

#### Update Template
```
PUT /templates/{template_id}
```

#### Delete Template
```
DELETE /templates/{template_id}
```

#### Clone Template
```
POST /templates/{template_id}/clone
```

**Request:**
```json
{
  "new_name": "my_cloned_template"
}
```

#### Validate Template
```
POST /templates/validate
```

Validates template structure without saving.

#### Export Template
```
GET /templates/{template_id}/export
```

Downloads template as JSON file.

#### Import Template
```
POST /templates/import
```

Upload template JSON to create new template.

---

### Video Rendering

#### Render Video
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
    "scene_1": "Round 1",
    "scene_2": "Round 2"
  },
  "audio": {
    "url": "https://example.com/music.mp3",
    "volume": 0.8,
    "fade_in": 2,
    "fade_out": 3,
    "loop": true
  },
  "webhook_url": "https://your-webhook.com/callback"
}
```

**Response (202):**
```json
{
  "status": "processing",
  "job_id": "abc123-def456-ghi789",
  "template_id": "fight_video_standard",
  "estimated_time_seconds": 80,
  "check_status_url": "/status/abc123-def456-ghi789",
  "webhook_url": "https://your-webhook.com/callback",
  "webhook_note": "You will receive a POST when job completes"
}
```

#### Check Job Status
```
GET /status/{job_id}
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

#### Download Video
```
GET /download/{job_id}
```

Returns the MP4 video file.

---

### Webhook Notifications

When you provide a `webhook_url` in your render request, the API will POST to that URL when the job completes or fails.

**Success Webhook:**
```json
{
  "event": "job_completed",
  "job_id": "abc123-def456-ghi789",
  "status": "completed",
  "template_id": "fight_video_standard",
  "download_url": "/download/abc123-def456-ghi789",
  "file_size_mb": 12.5,
  "duration_seconds": 80
}
```

**Failure Webhook:**
```json
{
  "event": "job_failed",
  "job_id": "abc123-def456-ghi789",
  "status": "failed",
  "template_id": "fight_video_standard",
  "error": {
    "message": "Failed to download image",
    "code": "IMAGE_DOWNLOAD_FAILED"
  }
}
```

---

### Utility Endpoints

#### Cleanup Old Files
```
POST /cleanup?hours=24
```

#### List All Jobs
```
GET /jobs
```

---

## Built-in Templates

### 1. fight_video_standard
- **8 scenes**, each with split-screen (3s) + split-screen (3s) + full winner (4s)
- **Total duration:** 80 seconds
- **Best for:** Tournament brackets, battle videos

### 2. fight_video_4_scenes
- **4 scenes**, same structure as standard
- **Total duration:** 40 seconds
- **Best for:** Shorter highlight videos

### 3. slideshow_simple
- **5 scenes**, each with single full-screen image (4s)
- **Total duration:** 20 seconds
- **Best for:** Photo slideshows, presentations

### 4. comparison_video
- **1 scene** with split-screen (5s) + split-screen (5s) + result (5s)
- **Total duration:** 15 seconds
- **Best for:** Before/after comparisons

---

## Creating Custom Templates

You can create your own templates to define exactly how your videos should be structured. Templates are reusable - create once, use many times with different images.

### Template Structure

```json
{
  "template_name": "my_template_name",
  "description": "What this template does",
  "scenes": [...],
  "output_settings": {...},
  "transitions": {...}
}
```

### Understanding Scenes and Segments

A **template** contains multiple **scenes**. Each **scene** contains multiple **segments**.

```
Template
├── Scene 1
│   ├── Segment 1 (split_top + split_bottom = split screen)
│   ├── Segment 2 (split_bottom - paired with above)
│   └── Segment 3 (full_winner = full screen image)
├── Scene 2
│   ├── Segment 1
│   ├── Segment 2
│   └── Segment 3
└── ... more scenes
```

### Segment Types

| Type | Description | Required Images |
|------|-------------|-----------------|
| `split_top` | Top half of split screen | `split_top` image |
| `split_bottom` | Bottom half of split screen | `split_bottom` image |
| `full_winner` | Full screen image | `full_winner` image |
| `full_screen` | Full screen (alias) | `full_screen` image |
| `full` | Full screen (alias) | `full` image |
| `image` | Generic full screen | `image` image |
| `result` | Result/outcome image | `result` image |

**Note:** `split_top` and `split_bottom` work together - they create a single split-screen video clip showing both images stacked vertically.

### Example 1: Simple Slideshow (3 images)

```json
{
  "template_name": "my_slideshow",
  "description": "Simple 3-image slideshow",
  "scenes": [
    {
      "scene_number": 1,
      "segments": [
        {"type": "image", "duration": 5, "position": "full_screen"}
      ]
    },
    {
      "scene_number": 2,
      "segments": [
        {"type": "image", "duration": 5, "position": "full_screen"}
      ]
    },
    {
      "scene_number": 3,
      "segments": [
        {"type": "image", "duration": 5, "position": "full_screen"}
      ]
    }
  ],
  "output_settings": {
    "width": 720,
    "height": 1280,
    "fps": 30
  }
}
```

**To use this template, provide:**
```json
{
  "template_id": "my_slideshow",
  "images": {
    "scene_1": {"image": "https://..."},
    "scene_2": {"image": "https://..."},
    "scene_3": {"image": "https://..."}
  }
}
```

### Example 2: VS Battle (2 fighters, 1 winner)

```json
{
  "template_name": "vs_battle",
  "description": "Two fighters face off, then winner revealed",
  "scenes": [
    {
      "scene_number": 1,
      "segments": [
        {"type": "split_top", "duration": 4, "position": "top_half"},
        {"type": "split_bottom", "duration": 4, "position": "bottom_half"},
        {"type": "full_winner", "duration": 5, "position": "full_screen"}
      ]
    }
  ],
  "output_settings": {
    "width": 720,
    "height": 1280,
    "fps": 30
  }
}
```

**To use this template, provide:**
```json
{
  "template_id": "vs_battle",
  "images": {
    "scene_1": {
      "split_top": "https://... (fighter 1)",
      "split_bottom": "https://... (fighter 2)",
      "full_winner": "https://... (winner image)"
    }
  }
}
```

### Example 3: Product Showcase (intro + features + CTA)

```json
{
  "template_name": "product_showcase",
  "description": "Product intro, 3 features, call to action",
  "scenes": [
    {
      "scene_number": 1,
      "segments": [
        {"type": "intro", "duration": 4, "position": "full_screen"}
      ]
    },
    {
      "scene_number": 2,
      "segments": [
        {"type": "feature1", "duration": 3, "position": "full_screen"}
      ]
    },
    {
      "scene_number": 3,
      "segments": [
        {"type": "feature2", "duration": 3, "position": "full_screen"}
      ]
    },
    {
      "scene_number": 4,
      "segments": [
        {"type": "feature3", "duration": 3, "position": "full_screen"}
      ]
    },
    {
      "scene_number": 5,
      "segments": [
        {"type": "cta", "duration": 5, "position": "full_screen"}
      ]
    }
  ],
  "output_settings": {
    "width": 1080,
    "height": 1920,
    "fps": 30
  }
}
```

**To use this template, provide:**
```json
{
  "template_id": "product_showcase",
  "images": {
    "scene_1": {"intro": "https://..."},
    "scene_2": {"feature1": "https://..."},
    "scene_3": {"feature2": "https://..."},
    "scene_4": {"feature3": "https://..."},
    "scene_5": {"cta": "https://..."}
  }
}
```

### Example 4: Tournament Bracket (4 rounds)

```json
{
  "template_name": "tournament_4_rounds",
  "description": "4-round tournament with matchups and winners",
  "scenes": [
    {
      "scene_number": 1,
      "segments": [
        {"type": "split_top", "duration": 2, "position": "top_half"},
        {"type": "split_bottom", "duration": 2, "position": "bottom_half"},
        {"type": "full_winner", "duration": 3, "position": "full_screen"}
      ]
    },
    {
      "scene_number": 2,
      "segments": [
        {"type": "split_top", "duration": 2, "position": "top_half"},
        {"type": "split_bottom", "duration": 2, "position": "bottom_half"},
        {"type": "full_winner", "duration": 3, "position": "full_screen"}
      ]
    },
    {
      "scene_number": 3,
      "segments": [
        {"type": "split_top", "duration": 2, "position": "top_half"},
        {"type": "split_bottom", "duration": 2, "position": "bottom_half"},
        {"type": "full_winner", "duration": 3, "position": "full_screen"}
      ]
    },
    {
      "scene_number": 4,
      "segments": [
        {"type": "split_top", "duration": 3, "position": "top_half"},
        {"type": "split_bottom", "duration": 3, "position": "bottom_half"},
        {"type": "full_winner", "duration": 5, "position": "full_screen"}
      ]
    }
  ],
  "output_settings": {
    "width": 720,
    "height": 1280,
    "fps": 30
  }
}
```

### Output Settings Reference

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `width` | integer | 720 | Video width in pixels (100-4096) |
| `height` | integer | 1280 | Video height in pixels (100-4096) |
| `fps` | integer | 30 | Frames per second (1-120) |
| `format` | string | "mp4" | Output format |
| `codec` | string | "libx264" | Video codec |

**Common Resolutions:**
- **720x1280** - Vertical/Portrait (TikTok, Reels, Shorts)
- **1080x1920** - Full HD Vertical
- **1280x720** - Horizontal/Landscape (YouTube)
- **1920x1080** - Full HD Horizontal

### Step-by-Step: Create Your First Template

**Step 1: Plan your video structure**
- How many scenes?
- What images in each scene?
- How long should each image show?

**Step 2: Create the template**
```bash
curl -X POST https://your-api.onrender.com/create-template \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "template_name": "my_first_template",
    "description": "My custom video template",
    "scenes": [
      {
        "scene_number": 1,
        "segments": [
          {"type": "image", "duration": 5, "position": "full_screen"}
        ]
      }
    ],
    "output_settings": {
      "width": 720,
      "height": 1280,
      "fps": 30
    }
  }'
```

**Step 3: Validate (optional)**
```bash
curl -X POST https://your-api.onrender.com/templates/validate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{ ... your template ... }'
```

**Step 4: Use your template**
```bash
curl -X POST https://your-api.onrender.com/render-video \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "template_id": "my_first_template",
    "images": {
      "scene_1": {
        "image": "https://your-image-url.com/image.png"
      }
    }
  }'
```

### Template Management Tips

1. **Clone existing templates** to customize them:
   ```bash
   curl -X POST https://api/templates/fight_video_standard/clone \
     -H "X-API-Key: your-key" \
     -d '{"new_name": "my_fight_template"}'
   ```

2. **Export templates** to back them up:
   ```bash
   curl https://api/templates/my_template/export -H "X-API-Key: your-key" > my_template.json
   ```

3. **Import templates** from JSON:
   ```bash
   curl -X POST https://api/templates/import \
     -H "X-API-Key: your-key" \
     -d @my_template.json
   ```

4. **Update templates** (non-default only):
   ```bash
   curl -X PUT https://api/templates/my_template \
     -H "X-API-Key: your-key" \
     -d '{"description": "Updated description", "scenes": [...]}'
   ```

### Common Mistakes to Avoid

1. **Mismatched segment types and images**
   - If template has `split_top`, you must provide `split_top` image
   - Segment type names must match exactly

2. **Missing scenes**
   - If template has 8 scenes, you must provide images for all 8
   - Use `scene_1`, `scene_2`, etc. as keys

3. **Invalid durations**
   - Duration must be positive number
   - Very long durations (>30s per segment) may timeout

4. **Wrong image format**
   - URLs must be HTTPS
   - Images should be PNG or JPG
   - Recommended: Match output resolution for best quality

---

## Audio Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `url` | string | - | HTTPS URL to audio file (MP3, WAV, AAC) |
| `volume` | number | 1.0 | Volume level (0.0 to 2.0) |
| `fade_in` | number | 0 | Fade in duration in seconds (0-30) |
| `fade_out` | number | 0 | Fade out duration in seconds (0-30) |
| `loop` | boolean | true | Loop audio to match video length |

---

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
| `UNAUTHORIZED` | 401 | Missing or invalid API key |
| `INVALID_REQUEST` | 400 | Missing or invalid request data |
| `INVALID_URL` | 400 | Invalid image/audio URL format |
| `MISSING_IMAGES` | 400 | Required images not provided |
| `INVALID_AUDIO` | 400 | Invalid audio settings |
| `INVALID_WEBHOOK_URL` | 400 | Invalid webhook URL |
| `TEMPLATE_NOT_FOUND` | 404 | Template does not exist |
| `JOB_NOT_FOUND` | 404 | Job ID not found |
| `VIDEO_NOT_READY` | 400 | Video still processing |
| `VIDEO_NOT_FOUND` | 404 | Video file was cleaned up |
| `TEMPLATE_EXISTS` | 409 | Template name already exists |
| `CANNOT_DELETE` | 403 | Cannot delete default template |
| `CANNOT_MODIFY` | 403 | Cannot modify default template |
| `QUEUE_FULL` | 503 | Job queue is at capacity |
| `FFMPEG_NOT_AVAILABLE` | 503 | FFmpeg not installed |
| `FFMPEG_ERROR` | 500 | FFmpeg processing failed |
| `IMAGE_DOWNLOAD_FAILED` | 500 | Could not download image |
| `SERVER_ERROR` | 500 | Unexpected server error |

---

## n8n Integration Example

### Workflow Steps:

1. **HTTP Request Node** - Submit render job:
   - Method: POST
   - URL: `https://your-api.onrender.com/render-video`
   - Headers: `X-API-Key: your-key`
   - Body: JSON with template_id, images, and webhook_url

2. **Option A: Webhook Trigger**
   - Use n8n webhook node to receive completion notification
   - No polling needed!

3. **Option B: Poll Status**
   - Wait Node (60 seconds)
   - HTTP Request to `/status/{job_id}`
   - IF Node to check if completed
   - Loop back to Wait if still processing

4. **HTTP Request Node** - Download video:
   - Method: GET
   - URL: `https://your-api.onrender.com/download/{job_id}`

5. **Google Drive Node** - Upload video

---

## Project Structure

```
/
├── app.py                      # Main Flask application with Swagger
├── config.py                   # Configuration settings
├── requirements.txt            # Python dependencies
├── render.yaml                 # Render deployment config
├── README.md                   # This file
├── .python-version             # Python version for Render
├── templates/                  # JSON template storage
│   ├── fight_video_standard.json
│   ├── fight_video_4_scenes.json
│   ├── slideshow_simple.json
│   └── comparison_video.json
├── services/
│   ├── __init__.py
│   ├── template_service.py     # Template CRUD operations
│   ├── video_service.py        # FFmpeg video rendering + webhooks
│   └── job_queue.py            # Background job processing
└── utils/
    ├── __init__.py
    ├── ffmpeg_builder.py       # FFmpeg command builder
    ├── validators.py           # Input validation
    └── cleanup.py              # File cleanup utilities
```

---

## Limitations (Free Tier)

- **Videos deleted on restart**: Render free tier doesn't persist storage
- **24-hour retention**: Videos auto-deleted after 24 hours
- **2 concurrent jobs**: Limited parallel processing
- **Cold starts**: First request after inactivity takes ~30 seconds

---

## Changelog

### v2.0.0
- Added API key authentication
- Added audio support with volume, fade in/out, looping
- Added webhook notifications
- Added template management (update, clone, validate, export/import)
- Added preset templates (4-scene, slideshow, comparison)
- Added Swagger documentation at `/docs`

### v1.0.0
- Initial release
- Basic template system
- Video rendering with split-screen and full-screen
- Job queue with status tracking

---

## License

MIT License
