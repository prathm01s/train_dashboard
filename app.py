from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient
from datetime import datetime
import paho.mqtt.client as mqtt
import threading

app = Flask(__name__)

# MongoDB Atlas (replace <username>, <password>, <cluster> with your credentials)
mongo_uri = "mongodb+srv://prathmeshsharma101:tlasaay123@callibration.lekgwp4.mongodb.net/"
mongo_client = MongoClient(mongo_uri)
db = mongo_client.train_system
collection = db.sensor_data
collection.create_index([("timestamp", -1), ("device", 1)])

# MQTT Configuration
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPICS = [
    "train/ultra1_distance", "train/ultra2_distance", "train/ultra1_obstacle", "train/ultra2_obstacle",
    "train/fire_flag", "train/power_state",
    "environment/tof1_distance", "environment/tof2_distance", "environment/broken_track_flag",
    "environment/power_station_flag", "environment/servo_state", "environment/stop"
]

current_data = {"train": {}, "environment": {}}

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"Connected to MQTT with code {rc}")
    for topic in MQTT_TOPICS:
        client.subscribe(topic)

def on_message(client, userdata, msg):
    global current_data
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        device, data_type = topic.split('/')[0], topic.split('/')[-1]
        current_data[device][data_type] = float(payload) if "distance" in data_type else int(payload)
        # Save data on complete message set or events
        if device == "train" and len(current_data["train"]) >= 6:
            data = {
                "device": "train",
                "ultra1_distance": current_data["train"].get("ultra1_distance", 0),
                "ultra2_distance": current_data["train"].get("ultra2_distance", 0),
                "ultra1_obstacle": current_data["train"].get("ultra1_obstacle", 0),
                "ultra2_obstacle": current_data["train"].get("ultra2_obstacle", 0),
                "fire_flag": current_data["train"].get("fire_flag", 0),
                "power_state": current_data["train"].get("power_state", 0),
                "timestamp": datetime.utcnow().isoformat()
            }
            collection.insert_one(data)
            current_data["train"] = {}
        if device == "environment" and len(current_data["environment"]) >= 5:
            data = {
                "device": "environment",
                "tof1_distance": current_data["environment"].get("tof1_distance", 0),
                "tof2_distance": current_data["environment"].get("tof2_distance", 0),
                "broken_track_flag": current_data["environment"].get("broken_track_flag", 0),
                "power_station_flag": current_data["environment"].get("power_station_flag", 0),
                "servo_state": current_data["environment"].get("servo_state", 0),
                "timestamp": datetime.utcnow().isoformat()
            }
            collection.insert_one(data)
            current_data["environment"] = {}
    except Exception as e:
        print(f"Error processing MQTT message: {e}")

mqtt_client = mqtt.Client(client_id="FlaskServer", protocol=mqtt.MQTTv5)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def run_mqtt():
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
    mqtt_client.loop_forever()

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
        data = list(collection.find().sort("timestamp", -1).limit(100))
        for item in data:
            item['_id'] = str(item['_id'])
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/all-data', methods=['GET'])
def get_all_data():
    try:
        skip = int(request.args.get('skip', 0))
        limit = int(request.args.get('limit', 100))
        data = list(collection.find().sort("timestamp", -1).skip(skip).limit(limit))
        for item in data:
            item['_id'] = str(item['_id'])
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)