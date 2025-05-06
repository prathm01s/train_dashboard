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
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(filename='app.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')

# MongoDB Atlas
mongo_uri = "mongodb+srv://prathmeshsharma101:tlasaay123@callibration.lekgwp4.mongodb.net/"
mongo_client = MongoClient(mongo_uri)
db = mongo_client.train_system

# Map MQTT topics to MongoDB collections
topic_to_collection = {
    "env/servo_turn": "env_servo_turn",
    "env/env_ultra": "env_env_ultra",
    "env/env_tof": "env_env_tof",
    "env/vib1": "env_vib1",
    "env/vib2": "env_vib2",
    "env/vib1_ones": "env_vib1_ones",
    "env/vib2_ones": "env_vib2_ones",
    "env/train_control": "env_train_control",
    "env/temperature": "env_temperature",
    "train/position": "train_position",
    "train/power_status": "train_power_status",
    "train/train_tof": "train_train_tof",
    "train/train_ultra": "train_train_ultra",
    "train/track_status": "train_track_status",
    "env/servo_control": "env_servo_control"
}

# Define collections
collections = {topic: db[coll] for topic, coll in topic_to_collection.items()}
collections["ml_metrics"] = db.ml_metrics

# MQTT Configuration
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPICS = list(topic_to_collection.keys())

# Local cache for latest 100 entries per topic
local_cache = {topic: deque(maxlen=100) for topic in MQTT_TOPICS + ["env/vib1_ones", "env/vib2_ones"]}

# Sliding windows for anomaly detection (10 readings)
windows = {topic: deque(maxlen=10) for topic in ['env/vib1', 'env/vib2']}

# Load pre-trained models and thresholds
autoencoder_models = {}
autoencoder_thresholds = {}
for col in ['env/vib1', 'env/vib2']:
    try:
        autoencoder_models[col] = tf.keras.models.load_model(f'models/{col}_model')
        with open(f'models/{col}_threshold.json', 'r') as f:
            autoencoder_thresholds[col] = json.load(f)['threshold']
        logging.info(f"Loaded autoencoder model and threshold for {col}")
    except Exception as e:
        logging.error(f"Error loading autoencoder model for {col}: {e}")
        autoencoder_models[col] = None
        autoencoder_thresholds[col] = None

def check_anomaly(sequence, model, threshold):
    try:
        sequence = np.array(sequence).reshape(1, -1, 100)
        reconstructed = model.predict(sequence, verbose=0)
        error = np.mean(np.abs(reconstructed - sequence))
        return bool(error > threshold)
    except Exception as e:
        logging.error(f"Error in anomaly detection: {e}")
        return False

def on_connect(client, userdata, flags, reason_code, properties=None):
    logging.info(f"Connected to MQTT with code {reason_code}")
    if reason_code == 0:
        for topic in MQTT_TOPICS:
            client.subscribe(topic)
            logging.info(f"Subscribed to {topic}")
    else:
        logging.error(f"MQTT connection failed: {reason_code}")

def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        timestamp = datetime.utcnow().isoformat()
        collection_name = topic_to_collection.get(topic)
        if not collection_name:
            logging.warning(f"Unknown topic: {topic}")
            return

        data = {'collection': topic, 'value': payload, 'timestamp': timestamp}
        logging.debug(f"Received message on {topic}: {payload}")

        # Check if the message includes a timestamp from ESP32
        if ',' in payload:
            parts = payload.split(',', 1)
            data['value'] = parts[0]
            data['esp_timestamp'] = parts[1]
            payload = parts[0]

        # Anomaly detection for vibration sensors
        if topic in autoencoder_models and autoencoder_models[topic] is not None:
            try:
                bit_array = [int(bit) for bit in payload[:100] if bit in '01']
                if len(bit_array) >= 100:
                    windows[topic].append(bit_array[:100])
                    if len(windows[topic]) == 10:
                        sequence = list(windows[topic])
                        is_anomaly = check_anomaly(sequence, autoencoder_models[topic], autoencoder_thresholds[topic])
                        if is_anomaly:
                            logging.warning(f"ALERT: Anomaly detected in {topic} - Bit String: {payload[:20]}...")
                        data['anomaly'] = is_anomaly
                else:
                    data['anomaly'] = False
            except ValueError:
                logging.warning(f"Invalid value in {topic}: {payload}")
                data['anomaly'] = False

        collections[topic].insert_one(data)
        local_cache[topic].append(data)
        logging.debug(f"Stored data in {collection_name}")
    except UnicodeDecodeError:
        logging.error(f"Error decoding MQTT payload for topic {topic}")
    except Exception as e:
        logging.error(f"Error processing MQTT message for topic {topic}: {e}")

# MQTT setup
mqtt_client = mqtt.Client(client_id="FlaskServer_" + str(random.randint(0, 0xffff)))
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def run_mqtt():
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
            logging.info("MQTT client connected")
            mqtt_client.loop_forever()
        except Exception as e:
            logging.error(f"MQTT connection failed: {e}")
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
        graph_collections = [
            "env/env_ultra", "env/env_tof", "env/vib1", "env/vib2",
            "env/temperature", "train/train_tof", "train/train_ultra"
        ]
        for topic in graph_collections:
            collection_data = list(collections[topic].find().sort("_id", -1).limit(20))
            for item in collection_data:
                item['_id'] = str(item['_id'])
                item['timestamp'] = item.get('timestamp', 'N/A')
                data.append(item)
        data.sort(key=lambda x: x.get('timestamp', 'N/A'), reverse=True)
        return jsonify(data[:100]), 200
    except Exception as e:
        logging.error(f"Error in /api/data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/cache/<topic>', methods=['GET'])
def get_cache(topic):
    try:
        if topic not in local_cache:
            return jsonify({"error": "Topic not found"}), 404
        cache_data = list(local_cache[topic])
        for item in cache_data:
            item['_id'] = str(item.get('_id', ''))
            item['timestamp'] = item.get('timestamp', 'N/A')
        return jsonify(cache_data), 200
    except Exception as e:
        logging.error(f"Error in /api/cache/{topic}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/all-data', methods=['GET'])
def get_all_data():
    try:
        skip = int(request.args.get('skip', 0))
        limit = int(request.args.get('limit', 100))
        if skip < 0 or limit <= 0:
            return jsonify({"error": "Invalid skip or limit parameters"}), 400
        data = []
        for topic in collections:
            if topic != "ml_metrics":
                collection_data = list(collections[topic].find().sort("_id", -1).skip(skip).limit(limit))
                for item in collection_data:
                    item['_id'] = str(item['_id'])
                    item['timestamp'] = item.get('timestamp', 'N/A')
                    data.append(item)
        data.sort(key=lambda x: x.get('timestamp', 'N/A'), reverse=True)
        return jsonify(data[:limit]), 200
    except Exception as e:
        logging.error(f"Error in /api/all-data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/collection/<collection_name>', methods=['GET'])
def get_collection_data(collection_name):
    try:
        topic = next((t for t, c in topic_to_collection.items() if c == collection_name), None)
        if topic not in collections:
            logging.warning(f"Collection not found: {collection_name}")
            return jsonify({"error": "Collection not found"}), 404
        data = list(collections[topic].find().sort("_id", -1).limit(1000))
        for item in data:
            item['_id'] = str(item['_id'])
            item['timestamp'] = item.get('timestamp', 'N/A')
        logging.debug(f"Fetched {len(data)} records for {collection_name}")
        return jsonify(data), 200
    except Exception as e:
        logging.error(f"Error in /api/collection/{collection_name}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/latest_position', methods=['GET'])
def get_latest_position():
    try:
        latest_position = collections['train/position'].find_one(sort=[('_id', -1)])
        if not latest_position:
            return jsonify({"position": "Unknown"}), 200
        return jsonify({"position": latest_position['value']}), 200
    except Exception as e:
        logging.error(f"Error in /api/latest_position: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/ml_thresholds', methods=['GET'])
def get_ml_thresholds():
    try:
        thresholds_data = {col: autoencoder_thresholds[col] for col in ['env/vib1', 'env/vib2'] if col in autoencoder_thresholds}
        logging.debug("Fetched ML thresholds")
        return jsonify(thresholds_data), 200
    except Exception as e:
        logging.error(f"Error in /api/ml_thresholds: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/ml_metrics', methods=['GET'])
def get_ml_metrics():
    try:
        metrics = list(collections["ml_metrics"].find().sort("_id", -1))
        for item in metrics:
            item['_id'] = str(item['_id'])
            item['timestamp'] = item.get('timestamp', 'N/A')
        logging.debug(f"Fetched {len(metrics)} ML metrics")
        return jsonify(metrics), 200
    except Exception as e:
        logging.error(f"Error in /api/ml_metrics: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/train/stop', methods=['POST'])
def train_stop():
    try:
        mqtt_client.publish("train/train_control", "1")
        logging.info("Published stop command to train/train_control")
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"Error publishing train stop: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/train/start', methods=['POST'])
def train_start():
    try:
        mqtt_client.publish("train/train_control", "0")
        logging.info("Published start command to train/train_control")
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"Error publishing train start: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/servo/30', methods=['POST'])
def servo_30():
    try:
        mqtt_client.publish("env/servo_control", "30")
        logging.info("Published servo to 30° command to env/servo_control")
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"Error publishing servo 30°: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/servo/0', methods=['POST'])
def servo_0():
    try:
        mqtt_client.publish("env/servo_control", "0")
        logging.info("Published servo to 0° command to env/servo_control")
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"Error publishing servo 0°: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)