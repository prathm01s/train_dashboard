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
const char* mqtt_server = "192.168.244.143"; // Laptop's IP
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
  "sw420",              // Vibration sensor (64-bit string)
  "env_ultra"           // Environmental ultrasonic (20 to 400 cm)
};
const int num_topics = 8;

// TOF1 position topics
const char* tof1_pos_topics[] = {
  "tof1_pos1", // ToF position 1 (0 to 200 cm)
  "tof1_pos2", // ToF position 2 (0 to 200 cm)
  "tof1_pos3", // ToF position 3 (0 to 200 cm)
  "tof1_pos4"  // ToF position 4 (0 to 200 cm)
};
const int tof1_position = 0; // Selects tof1_posX (0: tof1_pos1, 1: tof1_pos2, 2: tof1_pos3, 3: tof1_pos4)

// TOF2 position topics
const char* tof2_pos_topics[] = {
  "tof2_pos1", // ToF position 1 (0 to 200 cm)
  "tof2_pos2", // ToF position 2 (0 to 200 cm)
  "tof2_pos3", // ToF position 3 (0 to 200 cm)
  "tof2_pos4"  // ToF position 4 (0 to 200 cm)
};
const int tof2_position = 0; // Selects tof2_posX (0: tof2_pos1, 1: tof2_pos2, 2: tof2_pos3, 3: tof2_pos4)

// SW420 scenario topics
const char* sw420_scene_topics[] = {
  "sw420_scene1", // Scenario 1
  "sw420_scene2", // Scenario 2
  "sw420_scene3", // Scenario 3
  "sw420_scene4", // Scenario 4
  "sw420_scene5", // Scenario 5
  "sw420_scene6"  // Scenario 6
};
const int sw420_scenario = 0; // Selects sw420_sceneX (0: scene1, 1: scene2, ..., 5: scene6)

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
  if (strcmp(topic, "train_accelerometer") == 0) {
    float value = random(0, 100) / 10.0; // 0.0 to 10.0 g
    return String(value, 2);
  } else if (strcmp(topic, "train_ultra") == 0 || strcmp(topic, "env_ultra") == 0) {
    float value = random(20, 401); // 20 to 400 cm
    return String(value, 2);
  } else if (strcmp(topic, "train_infra") == 0) {
    float value = random(0, 1001); // 0 to 1000
    return String(value, 2);
  } else if (strcmp(topic, "tof1") == 0 || strcmp(topic, "tof2") == 0 ||
             strstr(topic, "tof1_pos") != NULL || strstr(topic, "tof2_pos") != NULL) {
    float value = random(0, 201); // 0 to 200 cm
    return String(value, 2);
  } else if (strcmp(topic, "dht") == 0) {
    float value = random(150, 351) / 10.0; // 15.0 to 35.0 °C
    return String(value, 2);
  } else if (strcmp(topic, "sw420") == 0 || strstr(topic, "sw420_scene") != NULL) {
    String bitString = "";
    for (int j = 0; j < 64; j++) {
      bitString += String(random(0, 2));
    }
    return bitString;
  } else {
    return "0.0"; // Default
  }
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

  // Publish data to main topics
  for (int i = 0; i < num_topics; i++) {
    String data = generateSensorData(mqtt_topics[i]);
    client.publish(mqtt_topics[i], data.c_str());
    Serial.print("Published to ");
    Serial.print(mqtt_topics[i]);
    Serial.print(": ");
    Serial.println(data);

    // Publish TOF1 to selected tof1_posX topic
    if (strcmp(mqtt_topics[i], "tof1") == 0 && tof1_position >= 0 && tof1_position < 4) {
      client.publish(tof1_pos_topics[tof1_position], data.c_str());
      Serial.print("Published to ");
      Serial.print(tof1_pos_topics[tof1_position]);
      Serial.print(": ");
      Serial.println(data);
    }

    // Publish TOF2 to selected tof2_posX topic
    if (strcmp(mqtt_topics[i], "tof2") == 0 && tof2_position >= 0 && tof2_position < 4) {
      client.publish(tof2_pos_topics[tof2_position], data.c_str());
      Serial.print("Published to ");
      Serial.print(tof2_pos_topics[tof2_position]);
      Serial.print(": ");
      Serial.println(data);
    }

    // Publish SW420 to selected sw420_sceneX topic
    if (strcmp(mqtt_topics[i], "sw420") == 0 && sw420_scenario >= 0 && sw420_scenario < 6) {
      client.publish(sw420_scene_topics[sw420_scenario], data.c_str());
      Serial.print("Published to ");
      Serial.print(sw420_scene_topics[sw420_scenario]);
      Serial.print(": ");
      Serial.println(data);
    }

    delay(100); // Small delay to avoid overwhelming the broker
  }

  delay(1000); // Publish every 1 second (adjusted for testing)
}