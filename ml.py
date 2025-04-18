import numpy as np
import tensorflow as tf
from pymongo import MongoClient
import json
import os
from datetime import datetime
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split

# MongoDB Atlas
mongo_uri = "mongodb+srv://prathmeshsharma101:tlasaay123@callibration.lekgwp4.mongodb.net/"
mongo_client = MongoClient(mongo_uri)
db = mongo_client.train_system

# Collections to process for thresholds
collections = ['env/tof1_pos1', 'env/tof1_pos2', 'env/tof1_pos3', 'env/tof1_pos4', 
               'env/tof2_pos1', 'env/tof2_pos2', 'env/tof2_pos3', 'env/tof2_pos4']

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
        tf.keras.layers.LSTM(128, activation='relu', input_shape=(10, 1), return_sequences=True),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.LSTM(64, activation='relu'),
        tf.keras.layers.RepeatVector(10),
        tf.keras.layers.LSTM(64, activation='relu', return_sequences=True),
        tf.keras.layers.LSTM(128, activation='relu', return_sequences=True),
        tf.keras.layers.TimeDistributed(tf.keras.layers.Dense(1))
    ])
    model.compile(optimizer='adam', loss='mse')
    early_stopping = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)
    history = model.fit(data, data, epochs=100, batch_size=32, validation_split=0.2, callbacks=[early_stopping], verbose=1)
    
    reconstructions = model.predict(data)
    errors = np.mean(np.abs(reconstructions - data), axis=(1, 2))
    threshold = np.mean(errors) + 2 * np.std(errors)
    
    try:
        os.makedirs('models', exist_ok=True)
        model_path = f'models/{collection_name}_model'
        threshold_path = f'models/{collection_name}_threshold.json'
        model.save(model_path)
        print(f"Saved autoencoder model to {model_path}")
        with open(threshold_path, 'w') as f:
            json.dump({'threshold': float(threshold)}, f)
        print(f"Saved threshold to {threshold_path}")
        
        # Store normal and anomalous readings
        values = fetch_data(collection_name)
        normal_indices = [i for i, err in enumerate(errors) if err < threshold]
        normal_readings = [float(values[i + 9]) for i in normal_indices if i + 9 < len(values)]
        anomalies = [float(values[i + 9]) for i in range(len(errors)) if errors[i] >= threshold and i + 9 < len(values)]
        with open(f'models/{collection_name}_normal.json', 'w') as f:
            json.dump(normal_readings, f)
        with open(f'models/{collection_name}_anomalies.json', 'w') as f:
            json.dump(anomalies, f)
    except Exception as e:
        print(f"Error saving model or threshold for {collection_name}: {e}")
    
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
        collection_name = f'env/sw420_scene{scene}'
        bit_strings = [doc['value'] for doc in db[collection_name].find() if 'value' in doc and len(doc['value']) == 64 and all(c in '01' for c in doc['value'])]
        for bit_string in bit_strings:
            array = np.array([int(bit) for bit in bit_string])
            data.append(array)
            labels.append(scene - 1)  # 0 to 5
    if len(data) == 0:
        print("No data for sw420 scenes")
        return
    data = np.array(data)
    labels = np.array(labels)
    
    X_train, X_val, y_train, y_val = train_test_split(data, labels, test_size=0.2, random_state=42)
    
    model = tf.keras.Sequential([
        tf.keras.layers.Dense(256, activation='relu', input_shape=(64,)),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(128, activation='relu'),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(6, activation='softmax')
    ])
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
    early_stopping = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)
    history = model.fit(X_train, y_train, epochs=100, batch_size=32, validation_data=(X_val, y_val), callbacks=[early_stopping], verbose=1)
    
    val_predictions = model.predict(X_val)
    thresholds = {}
    for scene in range(6):
        scene_indices = y_val == scene
        if np.any(scene_indices):
            scene_probs = val_predictions[scene_indices, scene]
            threshold = np.percentile(scene_probs, 10)
            thresholds[f'env/sw420_scene{scene + 1}'] = float(threshold)
        else:
            thresholds[f'env/sw420_scene{scene + 1}'] = 0.9
    
    try:
        os.makedirs('models', exist_ok=True)
        model_path = 'models/sw420_classifier'
        model.save(model_path)
        print(f"Saved sw420 classifier to {model_path}")
        for scene_name, threshold in thresholds.items():
            threshold_path = f'models/{scene_name}_threshold.json'
            with open(threshold_path, 'w') as f:
                json.dump({'threshold': threshold}, f)
            print(f"Saved threshold to {threshold_path}")
            db.thresholds.insert_one({
                "collectionName": scene_name,
                "threshold": threshold,
                "timestamp": datetime.utcnow().isoformat()
            })
        with open('models/sw420_classifier_metrics.json', 'w') as f:
            json.dump({
                'thresholds': thresholds,
                'final_accuracy': float(history.history['accuracy'][-1])
            }, f)
    except Exception as e:
        print(f"Error saving sw420 classifier or thresholds: {e}")
    
    metrics = {
        "collection": "sw420_classifier",
        "final_loss": float(history.history['loss'][-1]),
        "final_val_loss": float(history.history['val_loss'][-1]),
        "final_accuracy": float(history.history['accuracy'][-1]),
        "final_val_accuracy": float(history.history['val_accuracy'][-1]),
        "timestamp": datetime.utcnow().isoformat()
    }
    db.ml_metrics.insert_one(metrics)

def process_ultra(collection_name):
    values = fetch_data(collection_name)
    if len(values) < 10:
        print(f"Not enough data for {collection_name}")
        return
    kmeans = KMeans(n_clusters=4, random_state=42)
    kmeans.fit(values.reshape(-1, 1))
    labels = kmeans.labels_
    groups = []
    for i in range(4):
        cluster_values = values[labels == i]
        if len(cluster_values) > 0:
            groups.append({
                "group": i,
                "leftBound": float(np.min(cluster_values)),
                "rightBound": float(np.max(cluster_values)),
                "count": int(len(cluster_values))
            })
    distances = np.abs(values - kmeans.cluster_centers_[labels])
    threshold = np.mean(distances) + 2 * np.std(distances)
    anomalies = values[distances > threshold].tolist()
    
    try:
        os.makedirs('models', exist_ok=True)
        with open(f'models/{collection_name}_groups.json', 'w') as f:
            json.dump(groups, f)
        with open(f'models/{collection_name}_anomalies.json', 'w') as f:
            json.dump(anomalies, f)
        print(f"Saved groups and anomalies for {collection_name}")
    except Exception as e:
        print(f"Error saving groups or anomalies for {collection_name}: {e}")

def main():
    print(f"Current working directory: {os.getcwd()}")
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

    for base_col in ['env/tof1', 'env/tof2']:
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

    for ultra_col in ['train/ultra1', 'train/ultra2']:
        process_ultra(ultra_col)

    train_sw420_classifier()

if __name__ == "__main__":
    main()