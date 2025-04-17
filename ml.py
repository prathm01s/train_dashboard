import numpy as np
import tensorflow as tf
from pymongo import MongoClient
import json
import os

# MongoDB Atlas
mongo_uri = "mongodb+srv://prathmeshsharma101:tlasaay123@callibration.lekgwp4.mongodb.net/"
mongo_client = MongoClient(mongo_uri)
db = mongo_client.train_system

# Collections to process
collections = ['tof1_pos1', 'tof1_pos2', 'tof1_pos3', 'tof1_pos4']

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
    
    return model, threshold

def main():
    for col in collections:
        print(f"Training model for {col}...")
        values = fetch_data(col)
        if len(values) < 10:
            print(f"Not enough data for {col}")
            continue
        sequences = preprocess_data(values)
        model, threshold = train_autoencoder(sequences, col)
        print(f"Model for {col} trained. Threshold: {threshold}")

if __name__ == "__main__":
    main()