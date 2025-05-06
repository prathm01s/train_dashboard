#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>
#include <Wire.h>
#include <DHT.h>

// WiFi credentials
const char* ssid = "Doraemon";
const char* password = "helicopter";

// MQTT Broker settings
const char* mqtt_server = "192.168.156.143";
const int mqtt_port = 1883;
const char* mqtt_client_id = "env_esp";

// MQTT topics for publishing
const char* servo_turn_topic = "env/servo_turn";
const char* env_ultra_topic = "env/env_ultra";
const char* env_tof_topic = "env/env_tof";
const char* vib1_topic = "env/vib1";
const char* vib2_topic = "env/vib2";
const char* vib1_ones_topic = "env/vib1_ones";
const char* vib2_ones_topic = "env/vib2_ones";
const char* train_control_topic = "env/train_control";
const char* temperature_topic = "env/temperature";
const char* position_topic = "train/position";

// MQTT topics for subscription
const char* env_tof_sub = "env/env_tof";
const char* train_tof_sub = "train/train_tof";
const char* train_ultra_sub = "train/train_ultra";
const char* servo_control_sub = "env/servo_control";

// Sensor pins
const int env_ultra_trigPin = 27;
const int env_ultra_echoPin = 26;
const int env_tof_sdaPin = 21;
const int env_tof_sclPin = 22;
const int vibs_sensor_1 = 14;
const int vibs_sensor_2 = 13;
const int servo_turn_sensor = 19;
const int dhtPin = 16;

// DHT11 sensor
DHT dht(dhtPin, DHT11);

// Variables for servo logic
float env_tof_value = 0.0;
float train_tof_value = 0.0;
float train_ultra_value = 0.0;
const float TOF_LOWER_BOUND = 350.0; // mm
const float TOF_UPPER_BOUND = 490.0; // mm
const float TRAIN_ULTRA_THRESHOLD = 10.5; // cm
const float TRAIN_TOF_THRESHOLD = 9.7;  // cm
unsigned long lastManualCommand = 0;
const unsigned long MANUAL_OVERRIDE_DURATION = 5000; // 5 seconds

// Variables for vibration sensors
char vibs1_buffer[101];
char vibs2_buffer[101];
int vibs1_index = 0;
int vibs2_index = 0;
int prev_vib1_ones = 0;
int prev_vib2_ones = 0;

// Servo object
Servo servoTurn;
int servoAngle = 0;

// WiFi and MQTT clients
WiFiClient espClient;
PubSubClient client(espClient);

// Timing for sensor readings
unsigned long lastSensorRead = 0;
const unsigned long sensorInterval = 1000;

// Function prototypes
void reconnect();
void callback(char* topic, byte* payload, unsigned int length);
void vibs1Task(void *pvParameters);
void vibs2Task(void *pvParameters);
void vibsPublishTask(void *pvParameters);

void setup() {
  Serial.begin(115200);
  Serial.println("Starting env_esp setup...");

  // Initialize pins
  pinMode(env_ultra_trigPin, OUTPUT);
  pinMode(env_ultra_echoPin, INPUT);
  pinMode(vibs_sensor_1, INPUT);
  pinMode(vibs_sensor_2, INPUT);

  // Initialize DHT11 sensor
  dht.begin();

  // Initialize I2C for TOF sensor
  Wire.begin(env_tof_sdaPin, env_tof_sclPin);

  // Attach and test servo
  servoTurn.attach(servo_turn_sensor);
  Serial.println("Testing servo...");
  servoTurn.write(0);
  delay(500);
  servoTurn.write(30);
  delay(500);
  servoTurn.write(0);
  servoAngle = 0;
  Serial.println("Servo test complete, initialized to 0°");

  // Connect to WiFi
  Serial.print("Connecting to ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print("WiFi status: ");
    Serial.println(WiFi.status());
    attempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi connected");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi connection failed");
    ESP.restart();
  }

  // Set MQTT server and callback
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);

  // Create tasks for vibration sensors
  xTaskCreate(vibs1Task, "Vibs1Task", 4096, NULL, 1, NULL);
  xTaskCreate(vibs2Task, "Vibs2Task", 4096, NULL, 1, NULL);
  xTaskCreate(vibsPublishTask, "VibsPublishTask", 4096, NULL, 1, NULL);
}

void loop() {
  if (!client.connected()) {
    Serial.println("MQTT not connected, attempting reconnect...");
    reconnect();
  }
  client.loop();

  unsigned long currentMillis = millis();
  if (currentMillis - lastSensorRead >= sensorInterval) {
    // Read ultrasonic sensor
    digitalWrite(env_ultra_trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(env_ultra_trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(env_ultra_trigPin, LOW);
    long duration = pulseIn(env_ultra_echoPin, HIGH, 30000);
    float distance = (duration == 0) ? 9999.0 : (duration * 0.034 / 2);
    String ultraData = String(distance, 2);
    if (client.publish(env_ultra_topic, ultraData.c_str())) {
      Serial.print("Published Ultrasonic Distance (cm): ");
      Serial.println(distance, 2);
    }

    // Read TOF sensor
    Wire.beginTransmission(0x52);
    Wire.write(0x00);
    Wire.endTransmission();
    Wire.requestFrom(0x52, 2);
    int tofDistance = -1;
    if (Wire.available() >= 2) {
      int high = Wire.read();
      int low = Wire.read();
      tofDistance = (high << 8) | low;
    }
    String tofData = String(tofDistance);
    if (client.publish(env_tof_topic, tofData.c_str())) {
      Serial.print("Published TOF Distance (mm): ");
      Serial.println(tofDistance);
    }

    // Determine position based on sensor readings
    String position;
    if (distance >= 6.0 && distance <= 12.0) {
      position = "Position D";
    } else if (tofDistance >= 25 && tofDistance <= 60) {
      position = "Position A";
    } else if (tofDistance >= 350 && tofDistance <= 490) {
      position = "Position B";
    } else if (tofDistance >= 550 && tofDistance <= 670) {
      position = "Position C";
    } else {
      position = "Unknown";
    }
    if (client.publish(position_topic, position.c_str())) {
      Serial.print("Published Position: ");
      Serial.println(position);
    }

    // Read DHT11 sensor for temperature
    float temperature = dht.readTemperature();
    if (!isnan(temperature)) {
      String tempData = String(temperature, 2);
      if (client.publish(temperature_topic, tempData.c_str())) {
        Serial.print("Published Temperature: ");
        Serial.print(temperature, 2);
        Serial.println(" °C");
      }
    } else {
      Serial.println("Failed to read temperature from DHT11");
    }

    lastSensorRead = currentMillis;
  }
}

void reconnect() {
  int attempts = 0;
  while (!client.connected() && attempts < 10) {
    Serial.print("Attempting MQTT connection (attempt ");
    Serial.print(attempts + 1);
    Serial.println(")...");
    if (client.connect(mqtt_client_id)) {
      Serial.println("MQTT connected");
      client.subscribe(env_tof_sub);
      client.subscribe(train_tof_sub);
      client.subscribe(train_ultra_sub);
      client.subscribe(servo_control_sub);
      Serial.println("Subscribed to env_tof, train_tof, train_ultra, env/servo_control");
    } else {
      Serial.print("Failed, rc=");
      Serial.print(client.state());
      Serial.println(" Trying again in 5 seconds");
      delay(5000);
      attempts++;
    }
  }
  if (!client.connected()) {
    Serial.println("MQTT connection failed after max attempts");
  }
}

void callback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  message.trim(); // Remove whitespace
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(message);

  // Handle sensor data
  if (strcmp(topic, env_tof_sub) == 0) {
    env_tof_value = message.toFloat();
    Serial.print("Updated env_tof_value: ");
    Serial.println(env_tof_value);
  } else if (strcmp(topic, train_tof_sub) == 0) {
    train_tof_value = message.toFloat();
    Serial.print("Updated train_tof_value: ");
    Serial.println(train_tof_value);
  } else if (strcmp(topic, train_ultra_sub) == 0) {
    train_ultra_value = message.toFloat();
    Serial.print("Updated train_ultra_value: ");
    Serial.println(train_ultra_value);
  } else if (strcmp(topic, servo_control_sub) == 0) {
    int newAngle = -1;
    if (message == "0") {
      newAngle = 0;
    } else if (message == "30") {
      newAngle = 30;
    }
    if (newAngle == 0 || newAngle == 30) {
      servoTurn.write(newAngle);
      servoAngle = newAngle;
      lastManualCommand = millis();
      Serial.print("Manual servo command: Moved to ");
      Serial.print(newAngle);
      Serial.println(" degrees");
      String servoData = String(servoAngle);
      if (client.publish(servo_turn_topic, servoData.c_str())) {
        Serial.print("Published to env/servo_turn: ");
        Serial.println(servoData);
      }
    } else {
      Serial.println("Invalid servo angle received: " + message);
    }
  }

  // Automatic servo control (skipped during manual override)
  if (millis() - lastManualCommand > MANUAL_OVERRIDE_DURATION) {
    bool stopTrain = false;
    if (env_tof_value >= TOF_LOWER_BOUND && env_tof_value <= TOF_UPPER_BOUND) {
      if (train_ultra_value < TRAIN_ULTRA_THRESHOLD && train_tof_value < TRAIN_TOF_THRESHOLD) {
        stopTrain = true;
        Serial.println("Both train sensors detect obstacle, stopping train");
      } else if (train_ultra_value < TRAIN_ULTRA_THRESHOLD && servoAngle != 30) {
        servoAngle = 30;
        servoTurn.write(servoAngle);
        Serial.println("Train ultrasonic detects obstacle, servo to 30 degrees");
        String servoData = String(servoAngle);
        if (client.publish(servo_turn_topic, servoData.c_str())) {
          Serial.print("Published to env/servo_turn: ");
          Serial.println(servoData);
        }
      } else if (train_tof_value < TRAIN_TOF_THRESHOLD && servoAngle != 0) {
        servoAngle = 0;
        servoTurn.write(servoAngle);
        Serial.println("Train TOF detects obstacle, servo to 0 degrees");
        String servoData = String(servoAngle);
        if (client.publish(servo_turn_topic, servoData.c_str())) {
          Serial.print("Published to env/servo_turn: ");
          Serial.println(servoData);
        }
      }
    }
    if (stopTrain) {
      String controlData = "1";
      if (client.publish(train_control_topic, controlData.c_str())) {
        Serial.println("Published stop signal to env/train_control");
      }
    }
  }
}

void vibs1Task(void *pvParameters) {
  while (1) {
    if (vibs1_index < 100) {
      int val = digitalRead(vibs_sensor_1);
      vibs1_buffer[vibs1_index] = val + '0';
      vibs1_index++;
    }
    vTaskDelay(10 / portTICK_PERIOD_MS);
  }
}

void vibs2Task(void *pvParameters) {
  while (1) {
    if (vibs2_index < 100) {
      int val = digitalRead(vibs_sensor_2);
      vibs2_buffer[vibs2_index] = val + '0';
      vibs2_index++;
    }
    vTaskDelay(10 / portTICK_PERIOD_MS);
  }
}

void vibsPublishTask(void *pvParameters) {
  while (1) {
    vTaskDelay(1000 / portTICK_PERIOD_MS);
    if (vibs1_index >= 100 && vibs2_index >= 100) {
      vibs1_buffer[100] = '\0';
      vibs2_buffer[100] = '\0';

      String vib1_data = String(vibs1_buffer);
      String vib2_data = String(vibs2_buffer);
      if (client.publish(vib1_topic, vib1_data.c_str())) {
        Serial.print("Published Vibration Sensor 1 Bits: ");
        Serial.println(vibs1_buffer);
      }
      if (client.publish(vib2_topic, vib2_data.c_str())) {
        Serial.print("Published Vibration Sensor 2 Bits: ");
        Serial.println(vibs2_buffer);
      }

      int vib1_ones = 0;
      int vib2_ones = 0;
      for (int i = 0; i < 100; i++) {
        if (vibs1_buffer[i] == '1') vib1_ones++;
        if (vibs2_buffer[i] == '1') vib2_ones++;
      }
      String vib1_ones_data = String(vib1_ones);
      String vib2_ones_data = String(vib2_ones);
      if (client.publish(vib1_ones_topic, vib1_ones_data.c_str())) {
        Serial.print("Published Vibration Sensor 1 Ones: ");
        Serial.println(vib1_ones);
      }
      if (client.publish(vib2_ones_topic, vib2_ones_data.c_str())) {
        Serial.print("Published Vibration Sensor 2 Ones: ");
        Serial.println(vib2_ones);
      }

      vibs1_index = 0;
      vibs2_index = 0;
    } else {
      if (vibs1_index > 100) vibs1_index = 0;
      if (vibs2_index > 100) vibs2_index = 0;
    }
  }
}