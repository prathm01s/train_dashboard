import numpy as np
import tensorflow as tf
from pymongo import MongoClient
import json
import os
from datetime import datetime
from sklearn.cluster import KMeans

# MongoDB Atlas
mongo_uri = "mongodb+srv://prathmeshsharma101:tlasaay123@callibration.lekgwp4.mongodb.net/"
mongo_client = MongoClient(mongo_uri)
db = mongo_client.train_system

# Collections to process for thresholds
collections = ['tof1_pos1', 'tof1_pos2', 'tof1_pos3', 'tof1_pos4', 'tof2_pos1', 'tof2_pos2', 'tof2_pos3', 'tof2_pos4']

def fetch_data(collection_name):
    data = list(db[collection_name].find().sort("timestamp", -1))
    values = [float(doc['value']) for doc in data if 'value' in doc and doc['value'].replace('.', '', 1).isdigit()]
    return np.array(values)

def preprocess_data(values, window_size=10):
    sequences = []
    for i in range(len(values) - window_size + 1):
        sequences.append(values[i:i + window_size])
    return np.array(sequences).reshape(-1, window_size, 1)

def train_autoencoder(data, collection_name):
    model = tf.keras.Sequential([
        tf.keras.layers.LSTM(64, activation='relu', input_shape=(10, 1), return_sequences=True),
        tf.keras.layers.LSTM(32, activation='relu'),
        tf.keras.layers.RepeatVector(10),
        tf.keras.layers.LSTM(32, activation='relu', return_sequences=True),
        tf.keras.layers.LSTM(64, activation='relu', return_sequences=True),
        tf.keras.layers.TimeDistributed(tf.keras.layers.Dense(1))
    ])
    model.compile(optimizer='adam', loss='mse')
    history = model.fit(data, data, epochs=50, batch_size=32, validation_split=0.2, verbose=1)
    
    # Calculate reconstruction errors
    reconstructions = model.predict(data)
    errors = np.mean(np.abs(reconstructions - data), axis=(1, 2))
    threshold = np.mean(errors) + 2 * np.std(errors)
    
    # Save model and threshold
    os.makedirs('models', exist_ok=True)
    model.save(f'models/{collection_name}_model')
    with open(f'models/{collection_name}_threshold.json', 'w') as f:
        json.dump({'threshold': float(threshold)}, f)
    
    # Store metrics in MongoDB
    metrics = {
        "collection": collection_name,
        "final_loss": float(history.history['loss'][-1]),
        "final_val_loss": float(history.history['val_loss'][-1]),
        "threshold": float(threshold),
        "timestamp": datetime.utcnow().isoformat()
    }
    db.ml_metrics.insert_one(metrics)
    
    return model, threshold, errors

def train_sw420_classifier():
    data = []
    labels = []
    for scene in range(1, 7):
        collection_name = f'sw420_scene{scene}'
        bit_strings = [doc['value'] for doc in db[collection_name].find() if 'value' in doc and len(doc['value']) == 64]
        for bit_string in bit_strings:
            array = np.array([int(bit) for bit in bit_string])
            data.append(array)
            labels.append(scene - 1)  # 0 to 5
    if len(data) == 0:
        print("No data for sw420 scenes")
        return
    data = np.array(data)
    labels = np.array(labels)
    model = tf.keras.Sequential([
        tf.keras.layers.Dense(128, activation='relu', input_shape=(64,)),
        tf.keras.layers.Dense(64, activation='relu'),
        tf.keras.layers.Dense(6, activation='softmax')
    ])
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
    model.fit(data, labels, epochs=50, batch_size=32, validation_split=0.2)
    model.save('models/sw420_classifier')
    print("SW420 classifier trained and saved")

def main():
    for col in collections:
        print(f"Processing {col}...")
        values = fetch_data(col)
        if len(values) < 10:
            print(f"Not enough data for {col}")
            continue
        sequences = preprocess_data(values)
        model, threshold, errors = train_autoencoder(sequences, col)
        normal_indices = [i for i, err in enumerate(errors) if err < threshold]
        normal_last_readings = [values[i + 9] for i in normal_indices if i + 9 < len(values)]
        if len(normal_last_readings) > 0:
            left_bound = np.percentile(normal_last_readings, 1)
            right_bound = np.percentile(normal_last_readings, 99)
            db.thresholds.insert_one({
                "collectionName": col,
                "leftBound": float(left_bound),
                "rightBound": float(right_bound),
                "timestamp": datetime.utcnow().isoformat()
            })
            print(f"Threshold interval for {col}: [{left_bound}, {right_bound}]")
        else:
            print(f"No normal readings for {col}")

    # Process tof1 and tof2
    for base_col in ['tof1', 'tof2']:
        pos_cols = [f'{base_col}_pos{i}' for i in range(1, 5)]
        groups = []
        for i, pos_col in enumerate(pos_cols):
            threshold_doc = db.thresholds.find_one({"collectionName": pos_col})
            if threshold_doc:
                groups.append({
                    "group": i,
                    "leftBound": threshold_doc["leftBound"],
                    "rightBound": threshold_doc["rightBound"]
                })
        if groups:
            db.thresholds.insert_one({
                "collectionName": base_col,
                "groups": groups,
                "timestamp": datetime.utcnow().isoformat()
            })
            print(f"Groups for {base_col}: {groups}")

    # Process env_ultra
    values = fetch_data('env_ultra')
    if len(values) < 10:
        print("Not enough data for env_ultra")
    else:
        kmeans = KMeans(n_clusters=4)
        kmeans.fit(values.reshape(-1, 1))
        labels = kmeans.labels_
        groups = []
        for i in range(4):
            cluster_values = values[labels == i]
            if len(cluster_values) > 0:
                left_bound = np.min(cluster_values)
                right_bound = np.max(cluster_values)
                groups.append({
                    "group": i,
                    "leftBound": float(left_bound),
                    "rightBound": float(right_bound)
                })
        if groups:
            db.thresholds.insert_one({
                "collectionName": "env_ultra",
                "groups": groups,
                "timestamp": datetime.utcnow().isoformat()
            })
            print(f"Groups for env_ultra: {groups}")

    # Train SW420 classifier
    train_sw420_classifier()

if __name__ == "__main__":
    main()