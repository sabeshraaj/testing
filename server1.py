import asyncio
import websockets
import json
import threading
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
import time
import pvporcupine
import pyaudio
import struct
import os 
import webbrowser
import socket

app = Flask(__name__)
CORS(app)

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['school']
collection = db['medtech']

# Global variables
current_page = 'index.html'
connected_clients = set()
cached_data = None
browser_opened = False
websocket_loop = None

# Get local IP address
def get_local_ip():
    try:
        # Connect to a remote server to get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

# Load initial data and cache it
def load_initial_data():
    global cached_data
    try:
        docs = list(collection.find({}, {'_id': 0}).sort('timestamp', 1))
        cached_data = {
            'pulse_pressure': [doc['pulse_pressure'] for doc in docs],
            'temperature': [doc['temperature'] for doc in docs],
            'spo2': [doc['spo2'] for doc in docs],
            'respiratory_rate': [doc['respiratory_rate'] for doc in docs],
            'timestamps': [doc['timestamp'][:16].replace('T', ' ') for doc in docs]
        }
    except Exception as e:
        print(f"Error loading initial data: {e}")

# Watch for database changes
def watch_database_changes():
    global cached_data
    try:
        with collection.watch() as stream:
            for change in stream:
                if change['operationType'] == 'insert':
                    doc = change['fullDocument']
                    if cached_data:
                        cached_data['pulse_pressure'].append(doc['pulse_pressure'])
                        cached_data['temperature'].append(doc['temperature'])
                        cached_data['spo2'].append(doc['spo2'])
                        cached_data['respiratory_rate'].append(doc['respiratory_rate'])
                        cached_data['timestamps'].append(doc['timestamp'][:16].replace('T', ' '))
                        
                        if websocket_loop and connected_clients:
                            asyncio.run_coroutine_threadsafe(
                                broadcast_message(json.dumps({"type": "data_update", "data": cached_data})),
                                websocket_loop
                            )
    except Exception as e:
        print(f"Change stream error: {e}")

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

@app.route('/api/patient-data')
def get_patient_data():
    try:
        return jsonify(cached_data) if cached_data else jsonify({'error': 'No data available'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get-current-page')
def get_current_page():
    return jsonify({'currentPage': current_page})

# WebSocket handler
async def handle_client(websocket, path):
    print(f"New WebSocket client connected: {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"WebSocket client disconnected: {websocket.remote_address}")

async def broadcast_message(message):
    if connected_clients:
        print(f"Broadcasting to {len(connected_clients)} clients: {message}")
        disconnected = set()
        for client in connected_clients.copy():
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
            except Exception as e:
                print(f"Error sending message to client: {e}")
                disconnected.add(client)
        
        # Remove disconnected clients
        for client in disconnected:
            connected_clients.discard(client)

# Voice recognition using multiple Porcupine instances
def listen_for_wake_words():
    global current_page, browser_opened, websocket_loop

    try:
        configs = [
            ('index.html', 'hey apollo', '/home/sabeshraaj/Desktop/Demo/wakewords/hey-apollo.ppn', '2P2KEjdUqlI9quQH0ODXVYlQb5JVT4F5+R0U8guxE7u+J5K6Sd51uQ=='),
            ('patient_progress.html', 'patient progress', '/home/sabeshraaj/Desktop/Demo/wakewords/patient-progress.ppn', 'iFKjiqvfGAang4Gv2Q32o6kA4LfMgY5W4Pfp2vX3KFRDZ5T5mj5Oow=='),
            ('demonstration.html', 'show videos', '/home/sabeshraaj/Desktop/Demo/wakewords/show-videos.ppn', 'iyBDpOxuU5qOGP7t8wfrjhjH9XDzPFfQPjr1oteJ5XvIvxzEdHkMPQ==')
        ]

        porcupines = []
        for page, msg, keyword_path, access_key in configs:
            instance = pvporcupine.create(
                access_key=access_key,
                keyword_paths=[keyword_path],
                sensitivities=[0.65]
            )
            porcupines.append((page, msg, instance))

        pa = pyaudio.PyAudio()
        audio_stream = pa.open(
            rate=porcupines[0][2].sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=porcupines[0][2].frame_length
        )

        print("Voice recognition started. Listening for wake words...")

        while True:
            pcm = audio_stream.read(porcupines[0][2].frame_length, exception_on_overflow=False)
            pcm = struct.unpack_from("h" * porcupines[0][2].frame_length, pcm)

            for page, msg, porcupine_instance in porcupines:
                result = porcupine_instance.process(pcm)
                if result >= 0:
                    print(f"[Wake Word Detected] -> {msg} -> Navigate to: {page}")
                    current_page = page

                    # Only open browser if not already opened
                    if not browser_opened:
                        print("Opening browser for the first time...")
                        webbrowser.open(f"http://localhost:5000/")
                        browser_opened = True
                        time.sleep(3)  # Wait for browser to load
                    
                    # Send navigation message via WebSocket
                    if websocket_loop and connected_clients:
                        message = json.dumps({"type": "navigate", "page": page})
                        print(f"Sending WebSocket message: {message}")
                        asyncio.run_coroutine_threadsafe(
                            broadcast_message(message),
                            websocket_loop
                        )
                    else:
                        print(f"No WebSocket clients connected. Connected clients: {len(connected_clients)}")
                    
                    break

    except Exception as e:
        print(f"Error in voice recognition: {e}")
    finally:
        for _, _, p in porcupines:
            p.delete()
        if 'audio_stream' in locals():
            audio_stream.close()
        if 'pa' in locals():
            pa.terminate()

# Start WebSocket server
def start_websocket_server():
    global websocket_loop
    websocket_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(websocket_loop)
    
    async def run_server():
        print("Starting WebSocket server on ws://0.0.0.0:8080")
        server = await websockets.serve(handle_client, "0.0.0.0", 8080)
        print("WebSocket server is running...")
        await server.wait_closed()
    
    websocket_loop.run_until_complete(run_server())

if __name__ == '__main__':
    print("Starting Medical Tech Dashboard Server...")
    
    # Get and display local IP
    local_ip = get_local_ip()
    print(f"Local IP Address: {local_ip}")
    
    load_initial_data()

    # Start database watcher thread
    db_thread = threading.Thread(target=watch_database_changes, daemon=True)
    db_thread.start()
    print("Database watcher started")

    # Start WebSocket server thread
    ws_thread = threading.Thread(target=start_websocket_server, daemon=True)
    ws_thread.start()
    print("WebSocket server thread started")

    # Start voice recognition thread
    voice_thread = threading.Thread(target=listen_for_wake_words, daemon=True)
    voice_thread.start()
    print("Voice recognition thread started")

    # Give threads time to start
    time.sleep(2)

    # Run Flask app
    print(f"Starting Flask server on:")
    print(f"  Local:   http://localhost:5000")
    print(f"  Network: http://{local_ip}:5000")
    print(f"  Mobile:  http://{local_ip}:5000")
    print("\nPress Ctrl+C to stop the server")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
