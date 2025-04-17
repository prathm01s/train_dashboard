/*
 * ESP32 MQTT Publisher for Train System Dashboard
 * Publishes random sensor data to MQTT topics defined in app.py
 * Supports WPA2-Enterprise WiFi (e.g., university networks) using esp_eap_client
 * Compatible with broker.hivemq.com and Flask server
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <esp_eap_client.h> // Updated library for WPA2-Enterprise

// WiFi credentials for WPA2-Enterprise
const char* ssid = "wifi@iiith"; // Replace with your university WiFi SSID (e.g., "eduroam")
const char* wifi_username = "prathmesh.sharma@students.iiit.ac.in"; // Replace with your university username (e.g., "jdoe123@university.edu")
const char* wifi_password = "Msiay123/?-"; // Replace with your university password

// MQTT Broker settings
const char* mqtt_server = "broker.hivemq.com";
const int mqtt_port = 1883;
const char* mqtt_client_id = "ESP32_TrainSystem";

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
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(mqtt_client_id)) {
      Serial.println("connected");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
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

  // Connect to WiFi (WPA2-Enterprise)
  Serial.print("Connecting to ");
  Serial.println(ssid);

  // Configure WPA2-Enterprise
  WiFi.disconnect(true); // Clear previous WiFi settings
  WiFi.mode(WIFI_STA);   // Station mode

  // Set EAP identity, username, and password
  esp_eap_client_set_identity((uint8_t *)wifi_username, strlen(wifi_username));
  esp_eap_client_set_username((uint8_t *)wifi_username, strlen(wifi_username));
  esp_eap_client_set_password((uint8_t *)wifi_password, strlen(wifi_password));

  // Start WiFi connection with WPA2-Enterprise (PEAP-MSCHAPv2)
  WiFi.begin(ssid, WPA2_AUTH_PEAP, "", wifi_username, wifi_password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());

  // Set MQTT server
  client.setServer(mqtt_server, mqtt_port);

  // Seed random number generator
  randomSeed(analogRead(0));
}

void loop() {
  if (!client.connected()) {
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

  delay(5000); // Publish every 5 seconds
}