import numpy as np
import tensorflow as tf
from pymongo import MongoClient
import json
import os
from datetime import datetime
from sklearn.model_selection import train_test_split
import logging

# Configure logging
logging.basicConfig(filename='ml.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')

# MongoDB Atlas
mongo_uri = "mongodb+srv://prathmeshsharma101:tlasaay123@callibration.lekgwp4.mongodb.net/"
mongo_client = MongoClient(mongo_uri)
db = mongo_client.train_system

# Collections to process
collections = ['env_vib1', 'env_vib2']

def fetch_data(collection_name):
    try:
        data = list(db[collection_name].find().sort("timestamp", -1))
        values = [doc['value'] for doc in data if 'value' in doc and len(doc['value']) >= 100 and all(c in '01' for c in doc['value'][:100])]
        sequences = [[int(bit) for bit in value[:100]] for value in values]
        logging.debug(f"Fetched {len(sequences)} values from {collection_name}")
        return sequences
    except Exception as e:
        logging.error(f"Error fetching data from {collection_name}: {e}")
        return []

def preprocess_data(values, window_size=10, is_bit_string=True):
    try:
        if not values:
            return np.array([])
        sequences = []
        for i in range(len(values) - window_size + 1):
            seq = values[i:i + window_size]
            if all(len(s) == 100 for s in seq):
                sequences.append(seq)
        if not sequences:
            return np.array([])
        return np.array(sequences).reshape(-1, window_size, 100)
    except Exception as e:
        logging.error(f"Error preprocessing data: {e}")
        return np.array([])

def train_autoencoder(data, collection_name, is_bit_string=True):
    try:
        input_shape = (10, 100)
        model = tf.keras.Sequential([
            tf.keras.layers.LSTM(128, activation='relu', input_shape=input_shape, return_sequences=True),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.LSTM(64, activation='relu'),
            tf.keras.layers.RepeatVector(10),
            tf.keras.layers.LSTM(64, activation='relu', return_sequences=True),
            tf.keras.layers.LSTM(128, activation='relu', return_sequences=True),
            tf.keras.layers.TimeDistributed(tf.keras.layers.Dense(100))
        ])
        model.compile(optimizer='adam', loss='mse')
        early_stopping = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)
        history = model.fit(data, data, epochs=100, batch_size=32, validation_split=0.2, callbacks=[early_stopping], verbose=1)

        reconstructions = model.predict(data)
        errors = np.mean(np.abs(reconstructions - data), axis=(1, 2))
        threshold = np.mean(errors) + 2 * np.std(errors)

        os.makedirs('models', exist_ok=True)
        model_path = f'models/{collection_name}_model'
        threshold_path = f'models/{collection_name}_threshold.json'
        model.save(model_path)
        logging.info(f"Saved autoencoder model to {model_path}")
        with open(threshold_path, 'w') as f:
            json.dump({'threshold': float(threshold)}, f)
        logging.info(f"Saved threshold to {threshold_path}")

        metrics = {
            "collection": collection_name,
            "final_loss": float(history.history['loss'][-1]),
            "final_val_loss": float(history.history['val_loss'][-1]),
            "threshold": float(threshold),
            "timestamp": datetime.utcnow().isoformat()
        }
        db.ml_metrics.insert_one(metrics)
        logging.info(f"Stored metrics for {collection_name}")

        return model, threshold, errors
    except Exception as e:
        logging.error(f"Error training autoencoder for {collection_name}: {e}")
        return None, None, None

def main():
    logging.info(f"Starting ML processing in {os.getcwd()}")
    for col in collections:
        logging.info(f"Processing {col}...")
        values = fetch_data(col)
        if len(values) < 10:
            logging.warning(f"Not enough data for {col}")
            continue
        sequences = preprocess_data(values, is_bit_string=True)
        if sequences.size == 0:
            logging.warning(f"Failed to preprocess data for {col}")
            continue
        model, threshold, errors = train_autoencoder(sequences, col, is_bit_string=True)
        if model is None:
            continue

if __name__ == "__main__":
    main()