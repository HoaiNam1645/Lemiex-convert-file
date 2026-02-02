"""
PES Embroidery API Service
FastAPI-based REST API for PES file conversion and preview
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS, CORS_CREDENTIALS, CORS_METHODS, CORS_HEADERS, HOST, PORT
from routes import convert, preview, format, convert_b2, batch_convert, label_convert, qr_generate, merge_image, progress

app = FastAPI(
    title="PES Embroidery API",
    description="API service for converting PES embroidery files to JSON and generating previews",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=CORS_CREDENTIALS,
    allow_methods=CORS_METHODS,
    allow_headers=CORS_HEADERS,
)


@app.get("/pes-api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "pes-embroidery-api"}


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    import os
    import asyncio
    from services.background_store import get_store
    
    # Configure Progress Store
    store = get_store()
    dropbox_token = os.getenv("DROPBOX_ACCESS_TOKEN", "")
    dropbox_key = os.getenv("DROPBOX_ACCESS_KEY", "")
    dropbox_path = os.getenv("DROPBOX_PATH", "/.Embroidery_Lemiex")
    
    store.configure(
        root_path=dropbox_path,
        dropbox_token=dropbox_token,
        dropbox_key=dropbox_key
    )
    
    # Start background task
    asyncio.create_task(store.start_background_task())


# Include routers
app.include_router(convert.router, prefix="/pes-api", tags=["Convert"])
app.include_router(preview.router, prefix="/pes-api", tags=["Preview"])
app.include_router(format.router, prefix="/pes-api", tags=["Format"])
app.include_router(convert_b2.router, prefix="/pes-api", tags=["B2 Storage"])
app.include_router(batch_convert.router, prefix="/pes-api", tags=["Batch Convert"])
app.include_router(label_convert.router, prefix="/pes-api", tags=["Label Convert"])
app.include_router(qr_generate.router, prefix="/pes-api", tags=["QR Generate"])
app.include_router(merge_image.router, prefix="/pes-api", tags=["Merge Image"])
app.include_router(progress.router, prefix="/pes-api", tags=["Progress"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
