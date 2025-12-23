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
from routes import convert, preview, format, convert_b2

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


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "pes-embroidery-api"}


# Include routers
app.include_router(convert.router, prefix="/api", tags=["Convert"])
app.include_router(preview.router, prefix="/api", tags=["Preview"])
app.include_router(format.router, prefix="/api", tags=["Format"])
app.include_router(convert_b2.router, prefix="/api", tags=["B2 Storage"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
