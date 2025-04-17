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

# Define collections for each MQTT topic
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
    "tof2_pos1": db.tof2_pos1,
    "tof2_pos2": db.tof2_pos2,
    "tof2_pos3": db.tof2_pos3,
    "tof2_pos4": db.tof2_pos4,
    "sw420_scene1": db.sw420_scene1,
    "sw420_scene2": db.sw420_scene2,
    "sw420_scene3": db.sw420_scene3,
    "sw420_scene4": db.sw420_scene4,
    "sw420_scene5": db.sw420_scene5,
    "sw420_scene6": db.sw420_scene6,
    "ml_metrics": db.ml_metrics
}

# MQTT Configuration
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPICS = [
    "train_accelerometer", "train_ultra", "train_infra",
    "tof1", "tof2", "dht", "sw420", "env_ultra",
    "tof1_pos1", "tof1_pos2", "tof1_pos3", "tof1_pos4",
    "tof2_pos1", "tof2_pos2", "tof2_pos3", "tof2_pos4",
    "sw420_scene1", "sw420_scene2", "sw420_scene3",
    "sw420_scene4", "sw420_scene5", "sw420_scene6"
]

# Local cache for latest 100 entries per collection
local_cache = {topic: [] for topic in collections.keys()}

# Sliding windows for anomaly detection (10 readings)
windows = {col: deque(maxlen=10) for col in ['tof1_pos1', 'tof1_pos2', 'tof1_pos3', 'tof1_pos4',
                                             'tof2_pos1', 'tof2_pos2', 'tof2_pos3', 'tof2_pos4']}

# Load pre-trained models and thresholds from ml.py output
autoencoder_models = {}
autoencoder_thresholds = {}
for col in ['tof1_pos1', 'tof1_pos2', 'tof1_pos3', 'tof1_pos4',
            'tof2_pos1', 'tof2_pos2', 'tof2_pos3', 'tof2_pos4']:
    try:
        autoencoder_models[col] = tf.keras.models.load_model(f'models/{col}_model')
        with open(f'models/{col}_threshold.json', 'r') as f:
            autoencoder_thresholds[col] = json.load(f)['threshold']
    except Exception as e:
        print(f"Error loading autoencoder model for {col}: {e}")
        autoencoder_models[col] = None
        autoencoder_thresholds[col] = None

# Load sw420 classifier
try:
    sw420_classifier = tf.keras.models.load_model('models/sw420_classifier')
except Exception as e:
    print(f"Error loading sw420 classifier: {e}")
    sw420_classifier = None

# Function to check anomalies using autoencoder
def check_anomaly(sequence, model, threshold):
    sequence = np.array(sequence).reshape(1, 10, 1)
    reconstructed = model.predict(sequence, verbose=0)
    error = np.mean(np.abs(reconstructed - sequence))
    return error > threshold

# MQTT callbacks
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
        data = {'collection': topic, 'value': payload, 'timestamp': timestamp}

        if topic in collections:
            # Numerical data anomaly detection
            if topic in autoencoder_models and autoencoder_models[topic] is not None:
                data_value = float(payload)
                windows[topic].append(data_value)
                if len(windows[topic]) == 10:
                    sequence = list(windows[topic])
                    if check_anomaly(sequence, autoencoder_models[topic], autoencoder_thresholds[topic]):
                        print(f"ALERT: Anomaly detected in {topic} - Value: {payload} - Timestamp: {timestamp}")

            # Bit string anomaly detection
            elif topic.startswith('sw420') and sw420_classifier is not None:
                bit_string = payload
                if len(bit_string) == 64:
                    array = np.array([int(bit) for bit in bit_string]).reshape(1, 64)
                    prediction = sw420_classifier.predict(array, verbose=0)
                    max_prob = np.max(prediction)
                    if max_prob < 0.9:  # Threshold for anomaly
                        print(f"ALERT: Anomaly detected in {topic} - Bit String: {bit_string} - Timestamp: {timestamp}")

            # Store data in MongoDB and cache
            collections[topic].insert_one(data)
            local_cache[topic].append(data)
            if len(local_cache[topic]) > 100:
                local_cache[topic] = local_cache[topic][-100:]

    except Exception as e:
        print(f"Error processing MQTT message: {e}")

# MQTT setup
mqtt_client = mqtt.Client(client_id="FlaskServer_" + str(random.randint(0, 0xffff)))
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def run_mqtt():
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
            mqtt_client.loop_forever()
        except Exception as e:
            print(f"MQTT connection failed: {e}")
            time.sleep(10)

threading.Thread(target=run_mqtt, daemon=True).start()

# Flask routes
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
            data.extend(cache[-20:])
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