from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient
from datetime import datetime
import paho.mqtt.client as mqtt
import threading
import json
import numpy as np
import tensorflow as tf
from collections import deque
import time
import random

app = Flask(__name__)

# MongoDB Atlas
mongo_uri = "mongodb+srv://prathmeshsharma101:tlasaay123@callibration.lekgwp4.mongodb.net/"
mongo_client = MongoClient(mongo_uri)
db = mongo_client.train_system

# Define collections for each MQTT topic and aggregates
collections = {
    "train_accelerometer": db.train_accelerometer,
    "train_ultra": db.train_ultra,
    "train_infra": db.train_infra,
    "tof1": db.tof1,
    "tof2": db.tof2,
    "dht": db.dht,
    "sw420": db.sw420,
    "env_ultra": db.env_ultra,
    "trainESP": db.trainESP,
    "environmentESP": db.environmentESP,
    "tof1_pos1": db.tof1_pos1,
    "tof1_pos2": db.tof1_pos2,
    "tof1_pos3": db.tof1_pos3,
    "tof1_pos4": db.tof1_pos4,
    "ml_metrics": db.ml_metrics
}

# MQTT Configuration
MQTT_BROKER = "127.0.0.1"  # Replace with your laptop's IP, e.g., "192.168.244.143"
MQTT_PORT = 1883
MQTT_TOPICS = [
    "train_accelerometer", "train_ultra", "train_infra",
    "tof1", "tof2", "dht", "sw420", "env_ultra",
    "tof1_pos1", "tof1_pos2", "tof1_pos3", "tof1_pos4"
]

# Local cache for latest 100 entries per collection
local_cache = {topic: [] for topic in collections.keys()}

# Windows for anomaly detection
windows = {col: deque(maxlen=10) for col in ['tof1_pos1', 'tof1_pos2', 'tof1_pos3', 'tof1_pos4']}

# Load ML models and thresholds
models = {}
thresholds = {}
for col in ['tof1_pos1', 'tof1_pos2', 'tof1_pos3', 'tof1_pos4']:
    try:
        models[col] = tf.keras.models.load_model(f'models/{col}_model')
        with open(f'models/{col}_threshold.json', 'r') as f:
            thresholds[col] = json.load(f)['threshold']
    except Exception as e:
        print(f"Error loading model for {col}: {e}")
        models[col] = None
        thresholds[col] = None

def check_anomaly(sequence, model, threshold):
    if model is None or threshold is None:
        return False
    sequence = np.array(sequence).reshape(1, 10, 1)
    reconstructed = model.predict(sequence)
    error = np.abs(sequence[0, -1, 0] - reconstructed[0, -1, 0])
    return error > threshold

# Store current data for aggregate collections
current_data = {
    "trainESP": {},
    "environmentESP": {}
}

def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"Connected to MQTT with code {reason_code}")
    if reason_code == 0:
        for topic in MQTT_TOPICS:
            client.subscribe(topic)
    else:
        print(f"Connection failed: {reason_code}")

def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        timestamp = datetime.utcnow().isoformat()

        # Handle individual collections
        if topic in collections:
            data_value = float(payload) if topic in windows else payload
            if topic in windows:
                windows[topic].append(data_value)
                if len(windows[topic]) == 10 and models[topic] is not None:
                    sequence = list(windows[topic])
                    is_anomaly = check_anomaly(sequence, models[topic], thresholds[topic])
                else:
                    is_anomaly = False
                data = {'collection': topic, 'value': payload, 'timestamp': timestamp, 'anomaly': is_anomaly}
            else:
                data = {'collection': topic, 'value': payload, 'timestamp': timestamp}
            collections[topic].insert_one(data)
            local_cache[topic].append(data)
            if len(local_cache[topic]) > 100:
                local_cache[topic] = local_cache[topic][-100:]

        # Aggregate data for trainESP
        if topic in ["train_accelerometer", "train_ultra", "train_infra"]:
            current_data["trainESP"][topic] = payload
            if all(key in current_data["trainESP"] for key in ["train_accelerometer", "train_ultra", "train_infra"]):
                aggregate_data = {
                    "collection": "trainESP",
                    "train_accelerometer": current_data["trainESP"]["train_accelerometer"],
                    "train_ultra": current_data["trainESP"]["train_ultra"],
                    "train_infra": current_data["trainESP"]["train_infra"],
                    "timestamp": timestamp
                }
                collections["trainESP"].insert_one(aggregate_data)
                local_cache["trainESP"].append(aggregate_data)
                if len(local_cache["trainESP"]) > 100:
                    local_cache["trainESP"] = local_cache["trainESP"][-100:]
                current_data["trainESP"] = {}

        # Aggregate data for environmentESP
        elif topic in ["tof1", "tof2", "dht", "sw420", "env_ultra"]:
            current_data["environmentESP"][topic] = payload
            if all(key in current_data["environmentESP"] for key in ["tof1", "tof2", "dht", "sw420", "env_ultra"]):
                aggregate_data = {
                    "collection": "environmentESP",
                    "tof1": current_data["environmentESP"]["tof1"],
                    "tof2": current_data["environmentESP"]["tof2"],
                    "dht": current_data["environmentESP"]["dht"],
                    "sw420": current_data["environmentESP"]["sw420"],
                    "env_ultra": current_data["environmentESP"]["env_ultra"],
                    "timestamp": timestamp
                }
                collections["environmentESP"].insert_one(aggregate_data)
                local_cache["environmentESP"].append(aggregate_data)
                if len(local_cache["environmentESP"]) > 100:
                    local_cache["environmentESP"] = local_cache["environmentESP"][-100:]
                current_data["environmentESP"] = {}

    except Exception as e:
        print(f"Error processing MQTT message: {e}")

mqtt_client = mqtt.Client(client_id="FlaskServer_" + str(random.randint(0, 0xffff))) # Unique client ID
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def run_mqtt():
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
            mqtt_client.loop_forever()
        except Exception as e:
            print(f"MQTT connection failed: {e}")
            time.sleep(10)  # Wait 10 seconds before retrying

threading.Thread(target=run_mqtt, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def data():
    return render_template('data.html')

@app.route('/api/data', methods=['GET'])
def get_data():
    try:
        data = []
        for cache in local_cache.values():
            data.extend(cache[-20:])  # Latest 20 from each collection
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/collection/<collection_name>', methods=['GET'])
def get_collection_data(collection_name):
    if collection_name not in collections:
        return jsonify({"error": "Collection not found"}), 404
    data = list(collections[collection_name].find().sort("timestamp", -1).limit(1000))
    for item in data:
        item['_id'] = str(item['_id'])
    return jsonify(data), 200

@app.route('/api/ml_thresholds', methods=['GET'])
def get_ml_thresholds():
    thresholds_data = {col: thresholds[col] for col in ['tof1_pos1', 'tof1_pos2', 'tof1_pos3', 'tof1_pos4'] if col in thresholds}
    return jsonify(thresholds_data), 200

@app.route('/api/ml_metrics', methods=['GET'])
def get_ml_metrics():
    try:
        metrics = list(collections["ml_metrics"].find().sort("timestamp", -1))
        for item in metrics:
            item['_id'] = str(item['_id'])
        return jsonify(metrics), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)