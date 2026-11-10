from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import requests
from PIL import Image
import io
import os
from datetime import datetime

app = FastAPI(title="HermesXP Vision Dashboard Server")

# Mount static files (dashboard.html)
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("dashboard.html", "r") as f:
        return f.read()

@app.get("/api/status")
async def status():
    return {"services": "active", "dashboard": "v0.3", "vision": "enabled", "xp_endpoint": "screenshot-only"}

@app.get("/api/analyze")
async def analyze_screenshot():
    """Host-side vision analysis for XP screenshot. Returns CUA-style suggestions. No XP commands."""
    try:
        # Fetch live screenshot (cache buster not needed here)
        screenshot_url = "http://192.168.1.78:18768/screenshot.bmp"
        resp = requests.get(screenshot_url, timeout=5)
        resp.raise_for_status()
        
        # Simple PIL load for size (real LFM stub for now)
        img = Image.open(io.BytesIO(resp.content))
        width, height = img.size
        
        # Mock vision analysis with actionable coords based on typical XP dialog (from lessons)
        analysis = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "screenshot_size": f"{width}x{height}",
            "detected": ["XP dialog box", "OK button", "title bar"],
            "suggestions": [
                {
                    "action": "click_ok",
                    "coords": (620, 450),
                    "confidence": 0.92,
                    "reason": "Typical OK button location in XP dialogs per host vision"
                },
                {
                    "action": "close_window",
                    "coords": (780, 50),
                    "confidence": 0.85,
                    "reason": "Title bar close button"
                }
            ],
            "note": "Host-side only using local_multimodal stub. Real LFM integration next. No XP touched."
        }
        return JSONResponse(analysis)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e), "note": "Screenshot endpoint unavailable - using mock for tests"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
