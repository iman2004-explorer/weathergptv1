"""Convenience launcher: `python run.py` starts the API on http://localhost:8000"""
import uvicorn
from app.config import PORT

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=True)
