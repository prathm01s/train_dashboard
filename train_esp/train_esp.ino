#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>

// WiFi credentials
const char* ssid = "Doraemon";
const char* password = "helicopter";

// MQTT Broker settings
const char* mqtt_server = "192.168.156.143";
const int mqtt_port = 1883;
const char* mqtt_client_id = "train_esp";

// MQTT topics
const char* power_status_topic = "train/power_status";
const char* train_tof_topic = "train/train_tof";
const char* train_ultra_topic = "train/train_ultra";
const char* train_tof_sub = "train/train_tof";
const char* train_ultra_sub = "train/train_ultra";
const char* env_tof_sub = "env/env_tof";
const char* env_vib1_ones_sub = "env/vib1_ones";
const char* env_vib2_ones_sub = "env/vib2_ones";
const char* train_control_sub = "env/train_control";
const char* track_status_topic = "train/track_status";
const char* position_topic = "train/position";
const char* train_control_sub_new = "train/train_control"; // New topic for train control
int posBtof_low = 350;
int posBtof_high = 490;

// Sensor pins
const int RELAY_PIN = 18;
const int TRAIN_TOF_SDA_PIN = 21;
const int TRAIN_TOF_SCL_PIN = 22;
const int TRIG_PIN = 27;
const int ECHO_PIN = 34;

// Thresholds
const float ULTRA_THRESHOLD = 10.5;
const float TOF_THRESHOLD = 9.7;

// Relay status
int power_status = 0;
int previous_power_status = -1;

// Vibration counts
int vib1 = 0; // Number of 1s from env/vib1_ones
int vib2 = 0; // Number of 1s from env/vib2_ones

// Position tracking
String current_position = "Unknown";
String previous_position = "";

// Sensor data
float hcDistance = 9999.0;
float tofDistance = 9999.0;

// WiFi and MQTT clients
WiFiClient espClient;
PubSubClient client(espClient);

// Message buffers for publishing
char hcMsg[32];
char tofMsg[32];
char statusMsg[32];
char trackMsg[32];
char posMsg[32];
bool publishHcMsg = false;
bool publishTofMsg = false;
bool publishStatusMsg = false;
bool publishTrackMsg = false;
bool publishPosMsg = false;

// Timing for tasks and Serial output
unsigned long lastTask = 0;
unsigned long lastSerialOutput = 0;
const unsigned long taskInterval = 200; // 50ms for sensor checks
const unsigned long serialInterval = 1000; // 1s for Serial output

// HC-SR04 distance measurement
float getHCDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 30000); // Timeout after 30ms
  if (duration == 0) {
    Serial.println("HC-SR04 Error: No echo received");
    return 9999.0;
  }
  float distance = (duration * 0.0343) / 2;
  if (distance > 0 && distance < 1000) {
    return distance;
  }
  Serial.println("HC-SR04 Error: Invalid distance");
  return 9999.0;
}

// TOF10120 distance measurement
float getTOFDistance() {
  Wire.beginTransmission(0x52);
  Wire.write(0);
  if (Wire.endTransmission() != 0) {
    Serial.println("TOF10120 I2C Error: Failed to start transmission");
    return 9999.0;
  }
  Wire.requestFrom(0x52, 2);
  if (Wire.available() >= 2) {
    uint16_t highByte = Wire.read();
    uint16_t lowByte = Wire.read();
    uint16_t distance = (highByte << 8) + lowByte;
    float distance_cm = distance / 10.0;
    if (distance_cm > 0 && distance_cm < 2000) {
      return distance_cm;
    }
  }
  Serial.println("TOF10120 Error: Invalid reading or no data");
  return 9999.0;
}

int inServoDemons = 0;

// MQTT callback for incoming messages
void callback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  if (strcmp(topic, env_tof_sub) == 0) {
    float env_tof_value = message.toFloat() / 10.0; // Convert mm to cm
    if (env_tof_value >= posBtof_low && env_tof_value <= posBtof_high) {
      inServoDemons = 1;
    } else {
      inServoDemons = 0;
    }
  } else if (strcmp(topic, env_vib1_ones_sub) == 0) {
    vib1 = message.toInt();
    Serial.print("Vibration Sensor 1 Ones: ");
    Serial.println(vib1);
  } else if (strcmp(topic, env_vib2_ones_sub) == 0) {
    vib2 = message.toInt();
    Serial.print("Vibration Sensor 2 Ones: ");
    Serial.println(vib2);
  } else if (strcmp(topic, position_topic) == 0) {
    if (message != current_position) {
      current_position = message;
      snprintf(posMsg, sizeof(posMsg), "%s", current_position.c_str());
      publishPosMsg = true;
    }
  } else if (strcmp(topic, train_control_sub) == 0) {
    if (message.startsWith("1")) {
      power_status = 1;
      Serial.println("Received stop signal from env/train_control");
    }
  } else if (strcmp(topic, train_control_sub_new) == 0) {
    if (message == "0") {
      power_status = 0;
      Serial.println("Received start signal from train/train_control");
    } else if (message == "1") {
      power_status = 1;
      Serial.println("Received stop signal from train/train_control");
    }
  }

  digitalWrite(RELAY_PIN, power_status ? LOW : HIGH);
}

void setup() {
  power_status = 0;
  Serial.begin(115200);
  Serial.println("Train Control System Starting...");

  // Initialize pins
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH);

  // Initialize I2C
  Wire.begin(TRAIN_TOF_SDA_PIN, TRAIN_TOF_SCL_PIN);

  // Connect to WiFi
  Serial.print("Connecting to ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi connection failed");
    ESP.restart();
  }
  Serial.println("WiFi connected");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  // Set MQTT server and callback
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void reconnect() {
  int attempts = 0;
  while (!client.connected() && attempts < 5) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(mqtt_client_id)) {
      Serial.println("MQTT connected");
      client.subscribe(train_tof_sub);
      client.subscribe(train_ultra_sub);
      client.subscribe(env_tof_sub);
      client.subscribe(env_vib1_ones_sub);
      client.subscribe(env_vib2_ones_sub);
      client.subscribe(position_topic);
      client.subscribe(train_control_sub);
      client.subscribe(train_control_sub_new);
      Serial.println("Subscribed to train_tof, train_ultra, env_tof, env_vib1_ones, env_vib2_ones, train/position, env/train_control, train/train_control");
    } else {
      Serial.print("Failed, rc=");
      Serial.print(client.state());
      Serial.println(" Trying again in 5 seconds");
      delay(5000);
      attempts++;
    }
  }
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long currentMillis = millis();

  // Handle sensor tasks every 50ms
  if (currentMillis - lastTask >= taskInterval) {
    hcDistance = getHCDistance();
    tofDistance = getTOFDistance();

    snprintf(hcMsg, sizeof(hcMsg), "%.1f", hcDistance);
    snprintf(tofMsg, sizeof(tofMsg), "%.1f", tofDistance);
    publishHcMsg = true;
    publishTofMsg = true;

    bool ultra_below = (hcDistance < ULTRA_THRESHOLD);
    bool tof_below = (tofDistance < TOF_THRESHOLD);
    if (inServoDemons) {
      if (ultra_below && tof_below) {
        power_status = 1;
        digitalWrite(RELAY_PIN, LOW);
      }
    } else {
      if (ultra_below || tof_below) {
        power_status = 1;
        digitalWrite(RELAY_PIN, LOW);
      }
    }

    if (power_status != previous_power_status) {
      snprintf(statusMsg, sizeof(statusMsg), "%d", power_status);
      publishStatusMsg = true;
      previous_power_status = power_status;
      Serial.println(power_status ? "Train STOPPED - Object too close!" : "Train RUNNING - Path clear");
    }
    lastTask = currentMillis;
  }

  // Publish messages
  if (publishHcMsg) {
    if (client.publish(train_ultra_topic, hcMsg)) {
      publishHcMsg = false;
    } else {
      Serial.println("Failed to publish to train_ultra_topic");
    }
  }
  if (publishTofMsg) {
    if (client.publish(train_tof_topic, tofMsg)) {
      publishTofMsg = false;
    } else {
      Serial.println("Failed to publish to train_tof_topic");
    }
  }
  if (publishStatusMsg) {
    if (client.publish(power_status_topic, statusMsg)) {
      publishStatusMsg = false;
    } else {
      Serial.println("Failed to publish to power_status_topic");
    }
  }
  if (publishTrackMsg) {
    if (client.publish(track_status_topic, trackMsg)) {
      publishTrackMsg = false;  
    } else {
      Serial.println("Failed to publish to track_status_topic");
    }
  }
  if (publishPosMsg) {
    if (client.publish(position_topic, posMsg)) {
      publishPosMsg = false;
    } else {
      Serial.println("Failed to publish to position_topic");
    }
  }

  // Serial output every 1 second
  if (currentMillis - lastSerialOutput >= serialInterval) {
    Serial.print("HC-SR04: ");
    Serial.print(hcDistance);
    Serial.print(" cm, TOF10120: ");
    Serial.print(tofDistance);
    Serial.print(" cm, Power Status: ");
    Serial.println(power_status);
    lastSerialOutput = currentMillis;
  }
}