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

# Watch for database changes , mind you this according to my database structure, so change it accordingly as required.
def watch_database_changes(loop):
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
                        asyncio.run_coroutine_threadsafe(
                            broadcast_message(json.dumps({"type": "data_update", "data": cached_data})),
                            loop
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

@app.route('/patient_progress')
def get_patient_progress():
    return render_=


# WebSocket handler
async def handle_client(websocket, path):
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)

async def broadcast_message(message):
    if connected_clients:
        await asyncio.gather(
            *[client.send(message) for client in connected_clients.copy()],
            return_exceptions=True
        )

# Voice recognition using multiple Porcupine instances
def listen_for_wake_words(loop):
    global current_page

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
                sensitivities=[0.65] #change this accordingly to your mic
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

        while True:
            pcm = audio_stream.read(porcupines[0][2].frame_length, exception_on_overflow=False)
            pcm = struct.unpack_from("h" * porcupines[0][2].frame_length, pcm)

            for page, msg, porcupine_instance in porcupines:
                result = porcupine_instance.process(pcm)
                if result >= 0:
                    print(f"[Wake Word Detected] -> {msg}")
                    current_page = page

                    # Local path to the HTML file
                    local_file_path = os.path.abspath(page)
                    # Replace the webbrowser line with:
                    os.system(f"python -c \"import webbrowser; webbrowser.get().open('http://localhost:5000/{page}', new=0, autoraise=True)\"")

                    # Optional: still broadcast over WebSocket (if you want)
                    asyncio.run_coroutine_threadsafe(
                        broadcast_message(json.dumps({"type": "navigate", "page": page})),
                        loop
                    )
                    break

    finally:
        for _, _, p in porcupines:
            p.delete()
        audio_stream.close()
        pa.terminate()

# Start WebSocket server
def start_websocket_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    start_server = websockets.serve(handler, "0.0.0.0", 8080)
    loop.run_until_complete(start_server)
    loop.run_forever()

if __name__ == '__main__':
    load_initial_data()

    # Create a main event loop and use it in all threads
    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)

    # Start database watcher thread
    db_thread = threading.Thread(target=watch_database_changes, args=(main_loop,), daemon=True)
    db_thread.start()

    # Start WebSocket server thread
    ws_thread = threading.Thread(target=start_websocket_server, daemon=True)
    ws_thread.start()

    # Start voice recognition thread
    voice_thread = threading.Thread(target=listen_for_wake_words, args=(main_loop,), daemon=True)
    voice_thread.start()

    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
