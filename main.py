import uvicorn
from app import app

if __name__ == "__main__":
    # Ensure environment variables (token for gateway) are set
    uvicorn.run(app, host="0.0.0.0", port=8000)
