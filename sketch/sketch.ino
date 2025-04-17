/*
 * ESP32 MQTT Publisher for Train System Dashboard
 * Publishes random sensor data to MQTT topics defined in app.py
 * Uses WPA2-Personal WiFi (SSID and password)
 * Compatible with local Mosquitto broker and Flask server
 */

#include <WiFi.h>
#include <PubSubClient.h>

// WiFi credentials for WPA2-Personal
const char* ssid = "Doraemon";
const char* password = "helicopter";

// MQTT Broker settings (local Mosquitto)
const char* mqtt_server = "192.168.244.143"; // Replace with your laptop's IP, e.g., "192.168.1.100"
const int mqtt_port = 1883;
const char* mqtt_client_id = "ESP32_TrainSystem"; // Fixed client ID

// MQTT Topics from app.py
const char* mqtt_topics[] = {
  "train_accelerometer", // Accelerometer data (0.0 to 10.0 g)
  "train_ultra",         // Ultrasonic distance (20 to 400 cm)
  "train_infra",        // Infrared intensity (0 to 1000)
  "tof1",               // Time-of-Flight sensor 1 (0 to 200 cm)
  "tof2",               // Time-of-Flight sensor 2 (0 to 200 cm)
  "dht",                // Temperature (15.0 to 35.0 °C) or humidity (30.0 to 90.0 %)
  "sw420",              // Vibration sensor (0 or 1)
  "env_ultra",          // Environmental ultrasonic (20 to 400 cm)
  "tof1_pos1",          // ToF position 1 (0 to 200 cm)
  "tof1_pos2",          // ToF position 2 (0 to 200 cm)
  "tof1_pos3",          // ToF position 3 (0 to 200 cm)
  "tof1_pos4"           // ToF position 4 (0 to 200 cm)
};
const int num_topics = 12;

// WiFi and MQTT clients
WiFiClient espClient;
PubSubClient client(espClient);

// Reconnect to MQTT broker
void reconnect() {
  int attempts = 0;
  while (!client.connected() && attempts < 5) {
    Serial.print("Attempting MQTT connection to ");
    Serial.print(mqtt_server);
    Serial.print(":");
    Serial.print(mqtt_port);
    Serial.print(" with client ID ");
    Serial.println(mqtt_client_id);
    if (client.connect(mqtt_client_id)) {
      Serial.println("MQTT connected");
    } else {
      Serial.print("MQTT failed, rc=");
      Serial.print(client.state());
      Serial.print(" WiFi status=");
      Serial.println(WiFi.status());
      Serial.println("Trying again in 10 seconds");
      delay(10000); // Wait 10 seconds
      attempts++;
    }
  }
  if (!client.connected()) {
    Serial.println("MQTT connection failed after 5 attempts, halting");
    while (true); // Halt for debugging
  }
}

// Generate random sensor data based on topic
String generateSensorData(const char* topic) {
  float value;
  if (strcmp(topic, "train_accelerometer") == 0) {
    value = random(0, 100) / 10.0; // 0.0 to 10.0 g
  } else if (strcmp(topic, "train_ultra") == 0 || strcmp(topic, "env_ultra") == 0) {
    value = random(20, 401); // 20 to 400 cm
  } else if (strcmp(topic, "train_infra") == 0) {
    value = random(0, 1001); // 0 to 1000
  } else if (strcmp(topic, "tof1") == 0 || strcmp(topic, "tof2") == 0 ||
             strcmp(topic, "tof1_pos1") == 0 || strcmp(topic, "tof1_pos2") == 0 ||
             strcmp(topic, "tof1_pos3") == 0 || strcmp(topic, "tof1_pos4") == 0) {
    value = random(0, 201); // 0 to 200 cm
  } else if (strcmp(topic, "dht") == 0) {
    value = random(150, 351) / 10.0; // 15.0 to 35.0 °C
  } else if (strcmp(topic, "sw420") == 0) {
    value = random(0, 2); // 0 or 1
  } else {
    value = 0.0; // Default
  }
  return String(value, 2); // Convert to string with 2 decimal places
}

void setup() {
  Serial.begin(115200);

  // Connect to WiFi (WPA2-Personal)
  Serial.print("Connecting to ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print("WiFi status: ");
    Serial.println(WiFi.status()); // Print status code
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi connected");
    Serial.println("IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi connection failed");
    while (true); // Halt for debugging
  }

  // Set MQTT server
  client.setServer(mqtt_server, mqtt_port);

  // Seed random number generator
  randomSeed(analogRead(0));
}

void loop() {
  if (!client.connected()) {
    Serial.println("Reconnecting...");
    reconnect();
  }
  client.loop();

  // Publish data to each topic
  for (int i = 0; i < num_topics; i++) {
    String data = generateSensorData(mqtt_topics[i]);
    client.publish(mqtt_topics[i], data.c_str());
    Serial.print("Published to ");
    Serial.print(mqtt_topics[i]);
    Serial.print(": ");
    Serial.println(data);
    delay(100); // Small delay to avoid overwhelming the broker
  }

  delay(1000); // Publish every 15 seconds
}