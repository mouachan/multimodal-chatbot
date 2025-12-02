""" Backend for Knowledge Base Chat App """

import json
import logging
import os
import sys
import asyncio
import base64
import uuid
import tempfile
from pathlib import Path

import httpx
from dotenv import dotenv_values, load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import chatbot
from helpers import logging_config

# Load local env vars if present
load_dotenv()

# Initialize logger
logging_config()
_logger = logging.getLogger(__name__)

# Get config
config = {
    **dotenv_values(".env"),  # load shared development variables
    **dotenv_values(".env.secret"),  # load sensitive variables
    **os.environ,  # override loaded values with environment variables
}
_logger.info(f"Config loaded...")

# Load configuration from JSON file
config_file = config.get("CONFIG_FILE")
if config_file and os.path.exists(config_file):
    with open(config_file, "r") as file:
        config_data = json.load(file)
        config.update(config_data)
        _logger.info(f"Configuration loaded from {config_file}")
else:
    _logger.warning(f"Config file {config_file} not found or not specified")

# Get LLMs config
llms_config = config.get("llms")

# Initialize Chatbot
chatbot = chatbot.Chatbot(config, _logger)

# App creation
app = FastAPI()

origins = ["*"]
methods = ["*"]
headers = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=methods,
    allow_headers=headers,
)


# Connection Manager for Websockets
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()

#############################
# API Endpoints definitions #
#############################


# Status
@app.get("/health")
async def health():
    """Basic status"""
    return {"message": "Status:OK"}


@app.get("/api/llms")
async def get_llms():
    """Get llms"""
    return llms_config

# Temporary image storage for base64 to URL conversion
_image_cache = {}
_image_dir = Path(tempfile.gettempdir()) / "multimodal_images"
_image_dir.mkdir(exist_ok=True)

@app.post("/api/upload-image")
async def upload_image(data: dict):
    """Convert base64 image to temporary URL"""
    try:
        base64_data = data.get("image", "")
        if not base64_data or not base64_data.startswith("data:image"):
            raise HTTPException(status_code=400, detail="Invalid image data")
        
        # Extract image data (remove data:image/xxx;base64, prefix)
        header, encoded = base64_data.split(",", 1)
        image_format = header.split(";")[0].split("/")[1]  # Extract format (jpeg, png, etc.)
        
        # Decode base64
        image_bytes = base64.b64decode(encoded)
        
        # Generate unique filename
        image_id = str(uuid.uuid4())
        filename = f"{image_id}.{image_format}"
        filepath = _image_dir / filename
        
        # Save image
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        
        # Store in cache
        _image_cache[image_id] = filepath
        
        # Return URL (relative to the API base)
        # In production, this should be an absolute URL
        image_url = f"/api/images/{image_id}"
        return {"url": image_url, "id": image_id}
    except Exception as e:
        _logger.error(f"Error uploading image: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/images/{image_id}")
async def get_image(image_id: str):
    """Serve temporary image"""
    if image_id not in _image_cache:
        raise HTTPException(status_code=404, detail="Image not found")
    
    filepath = _image_cache[image_id]
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Image file not found")
    
    return FileResponse(filepath)


async def handle_client_request(websocket: WebSocket, data: dict):
    async for next_item in chatbot.stream(
        data["model"],
        data["messages"],
        data["language"],
    ):
        answer = json.dumps(next_item)
        await websocket.send_text(answer)


@app.websocket("/ws/query/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            data = json.loads(data)
            asyncio.create_task(handle_client_request(websocket, data))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        _logger.info(f"Client {client_id} disconnected")


# Serve React App (frontend)
class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        if len(sys.argv) > 1 and sys.argv[1] == "dev":
            # We are in Dev mode, proxy to the React dev server
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://localhost:9000/{path}")
            return Response(response.text, status_code=response.status_code)
        else:
            try:
                return await super().get_response(path, scope)
            except (HTTPException, StarletteHTTPException) as ex:
                if ex.status_code == 404:
                    return await super().get_response("index.html", scope)
                else:
                    raise ex


app.mount("/", SPAStaticFiles(directory="public", html=True), name="spa-static-files")

# Launch the FastAPI server
if __name__ == "__main__":
    from uvicorn import run

    port = int(os.getenv("PORT", "5000"))
    run("app:app", host="0.0.0.0", port=port)
