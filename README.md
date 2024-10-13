# Project Setup and Usage

This project connects to the OpenAI WebSocket API to send and receive real-time audio data, with the ability to transcribe and interact via voice. It uses Python's `pyaudio` for handling microphone and speaker streams and records interactions with a WebSocket server.

### Project Structure:
- **Audio Handling**: Captures audio from the microphone and plays back responses through the speaker.
- **WebSocket Communication**: Sends audio data to OpenAI's WebSocket API, processes responses, and handles transcriptions.
- **Threads**: Utilizes threading to handle real-time audio input/output and WebSocket communication concurrently.

### Requirements:
Ensure the following dependencies are installed:
```bash
uv venv
source .venv/bin/activate;source .env
uv pip install pyaudio websocket-client python-dotenv loguru pydantic
uv sync
uv run main.py
```# openai_realtime_api_chatbot
