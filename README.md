# Project Setup and Usage

This project connects to the OpenAI WebSocket API to send and receive real-time audio data, with the ability to transcribe and interact via voice. It uses Python's `pyaudio` for handling microphone and speaker streams and records interactions with a WebSocket server.

### Project Structure:
- **Audio Handling**: Captures audio from the microphone and plays back responses through the speaker.
- **WebSocket Communication**: Sends audio data to OpenAI's WebSocket API, processes responses, and handles transcriptions.
- **Threads**: Utilizes threading to handle real-time audio input/output and WebSocket communication concurrently.

### Requirements:
Ensure the following dependencies are installed and set:
1.	Create a .env file in the project root and add your OpenAI API key:
```bash
OPENAI_API_KEY=your_openai_api_key
```
2.	Run the bellow command
```bash
uv venv
source .venv/bin/activate;source .env
uv pip install pyaudio websocket-client python-dotenv loguru pydantic
uv sync
uv run main.py
```
