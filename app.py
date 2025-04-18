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
    "env/tof1": db.env_tof1,
    "env/tof1_pos1": db.env_tof1_pos1,
    "env/tof1_pos2": db.env_tof1_pos2,
    "env/tof1_pos3": db.env_tof1_pos3,
    "env/tof1_pos4": db.env_tof1_pos4,
    "env/tof2": db.env_tof2,
    "env/tof2_pos1": db.env_tof2_pos1,
    "env/tof2_pos2": db.env_tof2_pos2,
    "env/tof2_pos3": db.env_tof2_pos3,
    "env/tof2_pos4": db.env_tof2_pos4,
    "env/sw420": db.env_sw420,
    "env/sw420_scene1": db.env_sw420_scene1,
    "env/sw420_scene2": db.env_sw420_scene2,
    "env/sw420_scene3": db.env_sw420_scene3,
    "env/sw420_scene4": db.env_sw420_scene4,
    "env/sw420_scene5": db.env_sw420_scene5,
    "env/sw420_scene6": db.env_sw420_scene6,
    "env/env_infra": db.env_env_infra,
    "env/dht": db.env_dht,
    "env/servo_gate": db.env_servo_gate,
    "env/servo_turn": db.env_servo_turn,
    "train/accelero": db.train_accelero,
    "train/ultra1": db.train_ultra1,
    "train/ultra2": db.train_ultra2,
    "train/power_on": db.train_power_on,
    "ml_metrics": db.ml_metrics
}

# MQTT Configuration
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPICS = [
    "env/tof1", "env/tof1_pos1", "env/tof1_pos2", "env/tof1_pos3", "env/tof1_pos4",
    "env/tof2", "env/tof2_pos1", "env/tof2_pos2", "env/tof2_pos3", "env/tof2_pos4",
    "env/sw420", "env/sw420_scene1", "env/sw420_scene2", "env/sw420_scene3", "env/sw420_scene4", "env/sw420_scene5", "env/sw420_scene6",
    "env/env_infra", "env/dht", "env/servo_gate", "env/servo_turn",
    "train/accelero", "train/ultra1", "train/ultra2", "train/power_on"
]

# Local cache for latest 100 entries per collection
local_cache = {topic: [] for topic in collections.keys()}

# Sliding windows for anomaly detection (10 readings)
windows = {col: deque(maxlen=10) for col in ['env/tof1_pos1', 'env/tof1_pos2', 'env/tof1_pos3', 'env/tof1_pos4',
                                             'env/tof2_pos1', 'env/tof2_pos2', 'env/tof2_pos3', 'env/tof2_pos4']}

# Load pre-trained models and thresholds
autoencoder_models = {}
autoencoder_thresholds = {}
for col in ['env/tof1_pos1', 'env/tof1_pos2', 'env/tof1_pos3', 'env/tof1_pos4',
            'env/tof2_pos1', 'env/tof2_pos2', 'env/tof2_pos3', 'env/tof2_pos4']:
    try:
        autoencoder_models[col] = tf.keras.models.load_model(f'models/{col}_model')
        with open(f'models/{col}_threshold.json', 'r') as f:
            autoencoder_thresholds[col] = json.load(f)['threshold']
    except Exception as e:
        print(f"Error loading autoencoder model for {col}: {e}")
        autoencoder_models[col] = None
        autoencoder_thresholds[col] = None

# Load sw420 classifier and thresholds
try:
    sw420_classifier = tf.keras.models.load_model('models/sw420_classifier')
except Exception as e:
    print(f"Error loading sw420 classifier: {e}")
    sw420_classifier = None

sw420_thresholds = {}
for scene in range(1, 7):
    scene_name = f'env_sw420_scene{scene}'
    try:
        with open(f'models/{scene_name}_threshold.json', 'r') as f:
            sw420_thresholds[scene_name] = json.load(f)['threshold']
    except Exception as e:
        print(f"Error loading threshold for {scene_name}: {e}")
        sw420_thresholds[scene_name] = 0.9  # Default threshold

def check_anomaly(sequence, model, threshold):
    sequence = np.array(sequence).reshape(1, 10, 1)
    reconstructed = model.predict(sequence, verbose=0)
    error = np.mean(np.abs(reconstructed - sequence))
    return bool(error > threshold)

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
            if topic in autoencoder_models and autoencoder_models[topic] is not None:
                data_value = float(payload)
                windows[topic].append(data_value)
                if len(windows[topic]) == 10:
                    sequence = list(windows[topic])
                    is_anomaly = check_anomaly(sequence, autoencoder_models[topic], autoencoder_thresholds[topic])
                    if is_anomaly:
                        print(f"ALERT: Anomaly detected in {topic} - Value: {payload}")
                    data['anomaly'] = is_anomaly
            elif topic.startswith('env/sw420') and sw420_classifier is not None:
                bit_string = payload
                if len(bit_string) == 64 and all(c in '01' for c in bit_string):
                    array = np.array([int(bit) for bit in bit_string]).reshape(1, 64)
                    prediction = sw420_classifier.predict(array, verbose=0)
                    max_prob = float(np.max(prediction))
                    scene_number = int(np.argmax(prediction))
                    scene_name = f'env_sw420_scene{scene_number + 1}'
                    threshold = sw420_thresholds.get(scene_name, 0.9)
                    is_anomaly = bool(max_prob < threshold)
                    if is_anomaly:
                        print(f"ALERT: Anomaly detected in {topic} - Bit String: {bit_string}")
                    data['sceneNumber'] = scene_number
                    data['anomaly'] = is_anomaly
                    if topic != 'env/sw420':
                        data.pop('sceneNumber', None)

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

@app.route('/api/all-data', methods=['GET'])
def get_all_data():
    try:
        skip = int(request.args.get('skip', 0))
        limit = int(request.args.get('limit', 100))
        if skip < 0 or limit <= 0:
            return jsonify({"error": "Invalid skip or limit parameters"}), 400
        data = []
        for topic, cache in local_cache.items():
            sliced_data = cache[-skip-limit:-skip] if skip > 0 else cache[-limit:]
            data.extend(sliced_data)
        data.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(data[:limit]), 200
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
    thresholds_data = {col: autoencoder_thresholds[col] for col in ['env/tof1_pos1', 'env/tof1_pos2', 'env/tof1_pos3', 'env/tof1_pos4',
                                                                  'env/tof2_pos1', 'env/tof2_pos2', 'env/tof2_pos3', 'env/tof2_pos4'] if col in autoencoder_thresholds}
    thresholds_data.update({col: sw420_thresholds[col] for col in sw420_thresholds})
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