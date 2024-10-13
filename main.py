import os
import threading
import pyaudio
import queue
import base64
import json
import time
from websocket import create_connection, WebSocketConnectionClosedException
from dotenv import load_dotenv
import wave  # Added for audio recording
from prompt import ASSISTANT_INSTRUCTIONS
from config import get_settings
from loguru import logger


# Load environment variables from .env file
load_dotenv()


settings = get_settings()


# Audio buffer and queue
audio_buffer = bytearray()
microphone_queue = queue.Queue()

# Control event for stopping the threads
stop_event = threading.Event()

# Microphone control variables
microphone_reengage_time = 0
microphone_active = None


# Callback for microphone audio input stream
def microphone_callback(input_data, frame_count, time_info, status):
    global microphone_reengage_time, microphone_active

    if time.time() > microphone_reengage_time:
        if microphone_active is not True:
            logger.info("Microphone activated, capturing input audio.")
            microphone_active = True
        microphone_queue.put(input_data)
    else:
        if microphone_active is not False:
            logger.info("Microphone suppressed to avoid feedback.")
            microphone_active = False

    return (None, pyaudio.paContinue)


# Send microphone audio data to WebSocket in base64 format
def send_microphone_audio_to_websocket(websocket):
    try:
        logger.info("Starting to send microphone audio to WebSocket.")
        while not stop_event.is_set():
            if not microphone_queue.empty():
                audio_chunk = microphone_queue.get()
                encoded_audio = base64.b64encode(audio_chunk).decode("utf-8")
                message = json.dumps(
                    {"type": "input_audio_buffer.append", "audio": encoded_audio}
                )
                try:
                    websocket.send(message)
                except WebSocketConnectionClosedException:
                    logger.error(
                        "WebSocket connection closed unexpectedly during audio transmission."
                    )
                    break
                except Exception as error:
                    logger.error(f"Error while sending microphone audio: {error}")
            else:
                time.sleep(0.01)
        logger.info("Finished sending microphone audio.")
    except Exception as error:
        logger.error(f"Exception in send microphone audio thread: {error}")
    finally:
        logger.info("Exiting send microphone audio thread.")


# Callback for speaker output audio stream
def speaker_callback(output_data, frame_count, time_info, status):
    global audio_buffer, microphone_reengage_time

    audio_buffer_size_needed = frame_count * 2
    current_audio_buffer_size = len(audio_buffer)

    if current_audio_buffer_size >= audio_buffer_size_needed:
        audio_chunk = bytes(audio_buffer[:audio_buffer_size_needed])
        audio_buffer = audio_buffer[audio_buffer_size_needed:]
        microphone_reengage_time = time.time() + settings.mic_reengage_delay_ms / 1000
    else:
        audio_chunk = bytes(audio_buffer) + b"\x00" * (
            audio_buffer_size_needed - current_audio_buffer_size
        )
        audio_buffer.clear()

    return (audio_chunk, pyaudio.paContinue)


# Receive audio and text data from WebSocket and process it
def receive_from_websocket(websocket):
    global audio_buffer

    try:
        logger.info("Listening for events from WebSocket...")
        partial_transcripts = {}
        assistant_partial_transcripts = {}

        while not stop_event.is_set():
            try:
                message = websocket.recv()
                if not message:
                    logger.info("WebSocket closed or no more data from server.")
                    break

                message_data = json.loads(message)
                # if message_data:
                #     if (
                #         message_data.get("type", "") == "response.audio.delta"
                #         or message_data.get("type", "") == "error"
                #     ):
                #         continue
                #     logger.success(f"Received WebSocket message: {message_data}")

                event_type = message_data.get("type", "")

                # if event_type != "error":
                #     logger.debug(f"Received WebSocket event: {event_type}")

                # # Handle input audio transcription events
                # if event_type == "conversation.item.created":
                #     logger.debug(f"Conversation item created: {message_data}")
                #     transcript = message_data.get("transcript", "")
                #     logger.info(f"User said: {transcript}")

                if event_type == "response.audio_transcript.done":
                    transcript = message_data.get("transcript", "")
                    logger.success(f"ChatGPT said: {transcript}")

                elif event_type == "conversation.item.input_audio_transcription.failed":
                    error_message = message_data.get("error", {}).get("message", "")
                    logger.error(f"Transcription failed: {error_message}")

                # Handle assistant's text response events
                elif event_type == "response.audio_transcript.delta":
                    item_id = message_data.get("item_id")
                    delta = message_data.get("delta", "")
                    if item_id:
                        assistant_partial_transcripts.setdefault(item_id, "")
                        assistant_partial_transcripts[item_id] += delta
                        print(
                            f"Assistant: {assistant_partial_transcripts[item_id]}",
                            end="\r",
                        )

                elif event_type == "response.text.done":
                    item_id = message_data.get("item_id")
                    text = message_data.get("text", "")
                    logger.info(f"Assistant: {text}")
                    # Remove the partial transcript as it's completed
                    if item_id in assistant_partial_transcripts:
                        del assistant_partial_transcripts[item_id]

                # Handle assistant's audio response
                elif event_type == "response.audio.delta":
                    audio_delta = base64.b64decode(message_data["delta"])
                    audio_buffer.extend(audio_delta)

                elif event_type == "response.audio.done":
                    logger.info("AI finished responding with audio.")

            except WebSocketConnectionClosedException:
                logger.error(
                    "WebSocket connection closed unexpectedly while receiving data."
                )
                break
            except Exception as error:
                logger.error(f"Error while receiving data from WebSocket: {error}")
        logger.info("Reception from WebSocket completed.")
    except Exception as error:
        logger.error(f"Exception in receive thread: {error}")
    finally:
        logger.info("Exiting receive thread.")


# Connect to OpenAI WebSocket, send audio and receive responses
def connect_to_openai():
    websocket = None
    try:
        websocket = create_connection(
            settings.websocket_url,
            header=[
                f"Authorization: Bearer {settings.openai_api_key}",
                "OpenAI-Beta: realtime=v1",
            ],
        )
        logger.info("Successfully connected to OpenAI WebSocket.")

        # Update session configuration to enable input audio transcription
        websocket.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "modalities": ["audio"],
                        "voice": "alloy",
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16",

                        "instructions": ASSISTANT_INSTRUCTIONS,
                        "input_audio_transcription": {
                            "model": "whisper-1",
                        },
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 200,
                        },
                        "temperature": 0.8,
                        "max_response_output_tokens": "inf",
                        "tools": [],
                        "tool_choice": "auto",
                    },
                }
            )
        )

        receive_thread = threading.Thread(
            target=receive_from_websocket, args=(websocket,)
        )
        receive_thread.start()

        send_thread = threading.Thread(
            target=send_microphone_audio_to_websocket, args=(websocket,)
        )
        send_thread.start()

        # Simulate client-side turn detection by committing audio buffers
        def simulate_turn_detection():
            while not stop_event.is_set():
                time.sleep(3)  # Adjust this time based on expected speech duration
                try:
                    websocket.send(json.dumps({"type": "input_audio_buffer.commit"}))
                    logger.info("Committed input audio buffer.")
                except Exception as error:
                    logger.error(f"Error while committing audio buffer: {error}")
                    break

        turn_detection_thread = threading.Thread(target=simulate_turn_detection)
        turn_detection_thread.start()

        while not stop_event.is_set():
            time.sleep(0.1)

        logger.info("Sending WebSocket close frame.")
        websocket.send_close()

        receive_thread.join()
        send_thread.join()
        turn_detection_thread.join()

        logger.info("WebSocket closed and threads terminated.")
    except Exception as error:
        logger.error(f"Failed to connect to OpenAI: {error}")
    finally:
        if websocket is not None:
            try:
                websocket.close()
                logger.info("WebSocket connection closed.")
            except Exception as error:
                logger.error(f"Error closing WebSocket connection: {error}")


def main():
    py_audio = pyaudio.PyAudio()

    microphone_stream = py_audio.open(
        format=settings.audio_format,
        channels=1,
        rate=settings.sample_rate,
        input=True,
        stream_callback=microphone_callback,
        frames_per_buffer=settings.chunk_size,
    )

    speaker_stream = py_audio.open(
        format=settings.audio_format,
        channels=1,
        rate=settings.sample_rate,
        output=True,
        stream_callback=speaker_callback,
        frames_per_buffer=settings.chunk_size,
    )

    try:
        microphone_stream.start_stream()
        speaker_stream.start_stream()

        logger.info("Audio streams started.")
        connect_to_openai()

        while microphone_stream.is_active() and speaker_stream.is_active():
            time.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")
        stop_event.set()

    finally:
        microphone_stream.stop_stream()
        microphone_stream.close()
        speaker_stream.stop_stream()
        speaker_stream.close()

        py_audio.terminate()
        logger.info("Audio streams stopped and resources released.")


if __name__ == "__main__":
    main()
