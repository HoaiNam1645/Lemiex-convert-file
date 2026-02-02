"""
Background Store for Progress API
Provides in-memory caching and periodic background refresh for embroidery progress data.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import re

from .progress_scanner import (
    ProgressSnapshot,
    ProgressCollector,
    LemiexClient,
    DropboxPesScanner,
    DropboxTokenProvider,
    PesScanner
)

LOGGER = logging.getLogger("api.store")

class ProgressStore:
    _instance = None
    
    def __init__(self):
        self._data: Optional[Dict[str, Any]] = None
        self._last_updated: float = 0
        self._is_updating: bool = False
        self._root_path: str = ""
        self._dropbox_token: str = ""
        self._dropbox_key: str = ""
        
        # Configuration
        self.UPDATE_INTERVAL_SECONDS = 60
        self.DAYS_LIMIT = 30  # Scan only recent 30 days
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ProgressStore()
        return cls._instance
        
    def configure(self, root_path: str, dropbox_token: str, dropbox_key: str):
        self._root_path = root_path
        self._dropbox_token = dropbox_token
        self._dropbox_key = dropbox_key
        
    def get_data(self) -> Dict[str, Any]:
        """Get current cached data. If empty, return status indicating loading."""
        if self._data is None:
            return {
                "status": "loading",
                "message": "Data is initializing..."
            }
        
        # Add metadata about freshness
        age = time.time() - self._last_updated
        self._data["cache_age_seconds"] = round(age, 1)
        return self._data
        
    async def start_background_task(self):
        """Start the periodic background update task."""
        LOGGER.info("Starting background progress scanner task")
        while True:
            try:
                await self.update_now()
            except Exception as e:
                LOGGER.error(f"Error in background update: {e}")
            
            # Wait for next interval
            await asyncio.sleep(self.UPDATE_INTERVAL_SECONDS)
            
    async def update_now(self):
        """Force an immediate update."""
        if self._is_updating:
            LOGGER.info("Update already in progress, skipping")
            return
            
        self._is_updating = True
        try:
            LOGGER.info("Running background scan...")
            start_time = time.time()
            
            # Run the scan (this is synchronous, so we run it in thread pool to not block async loop)
            loop = asyncio.get_running_loop()
            snapshot = await loop.run_in_executor(None, self._perform_scan)
            
            if snapshot:
                self._data = snapshot.to_dict(source=f"Dropbox (Cached {datetime.now().strftime('%H:%M:%S')})")
                self._last_updated = time.time()
                LOGGER.info(f"Background scan completed in {time.time() - start_time:.2f}s")
                
        except Exception as e:
            LOGGER.error(f"Background scan failed: {e}", exc_info=True)
        finally:
            self._is_updating = False
            
    def _perform_scan(self) -> Optional[ProgressSnapshot]:
        """Synchronous scan function to be run in executor."""
        # Setup scanner
        token_provider = DropboxTokenProvider(self._dropbox_token, self._dropbox_key)
        
        # Determine scan mode
        scanner = None
        if token_provider.ensure_token():
            # Use Dropox Scanner
            # TODO: Add date filtering logic to DropboxPesScanner
            scanner = DropboxPesScanner(token_provider, self._root_path)
            # Inject days limit into scanner
            scanner.set_days_limit(self.DAYS_LIMIT)
        else:
            # Fallback to local
            scanner = PesScanner(self._root_path)
            
        client = LemiexClient()
        collector = ProgressCollector(scanner, client)
        return collector.collect()

# Global accessor
def get_store() -> ProgressStore:
    return ProgressStore.get_instance()
