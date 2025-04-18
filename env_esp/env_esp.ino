#include <WiFi.h>
#include <PubSubClient.h>
#include <Servo.h>

// WiFi credentials
const char* ssid = "Doraemon";
const char* password = "helicopter";

// MQTT Broker settings
const char* mqtt_server = "192.168.244.143";
const int mqtt_port = 1883;
const char* mqtt_client_id = "env_esp";

// Topics for env_esp
const char* tof1_topic = "env/tof1";
const char* tof2_topic = "env/tof2";
const char* sw420_topic = "env/sw420";
const char* env_infra_topic = "env/env_infra";
const char* dht_topic = "env/dht";
const char* servo_gate_topic = "env/servo_gate";
const char* servo_turn_topic = "env/servo_turn";
const char* tof1_pos_topics[] = {"env/tof1_pos1", "env/tof1_pos2", "env/tof1_pos3", "env/tof1_pos4"};
const char* tof2_pos_topics[] = {"env/tof2_pos1", "env/tof2_pos2", "env/tof2_pos3", "env/tof2_pos4"};
const char* sw420_scene_topics[] = {"env/sw420_scene1", "env/sw420_scene2", "env/sw420_scene3", "env/sw420_scene4", "env/sw420_scene5", "env/sw420_scene6"};

// Control topics
const char* control_topics[] = {"control/env/servo_gate", "control/env/servo_turn"};

// Configuration for position/scene selection
const int tof1_position = 0; // Selects tof1_posX (0-3)
const int tof2_position = 0; // Selects tof2_posX (0-3)
const int sw420_scenario = 0; // Selects sw420_sceneX (0-5)

// Subscribed topics from train_esp
const char* train_topics[] = {"train/accelero", "train/ultra1", "train/ultra2", "train/power_on"};

// Global variables for received data from train_esp
float train_accelero = 0.0;
float train_ultra1 = 0.0;
float train_ultra2 = 0.0;
int train_power_on = 0;

// Servo flags
int servo_gate = 0;
int servo_turn = 0; // Can be set manually or via MQTT

// Threshold for servo_gate activation
float servo_infra_threshold = 100.0; // Example value, adjust as needed

// Servo objects and pins
Servo servoGate;
Servo servoTurn;
const int SERVO_GATE_PIN = 12;
const int SERVO_TURN_PIN = 13;

// WiFi and MQTT clients
WiFiClient espClient;
PubSubClient client(espClient);

// Function prototypes
void reconnect();
void callback(char* topic, byte* payload, unsigned int length);
void servoTask(void *pvParameters);
String generateSensorData(const char* topic);
float readEnvInfra();
void moveServoGate();
void moveServoTurn();

void setup() {
  Serial.begin(115200);

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
    Serial.println("IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi connection failed");
    while (true);
  }

  // Set MQTT server and callback
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);

  // Attach servos
  servoGate.attach(SERVO_GATE_PIN);
  servoTurn.attach(SERVO_TURN_PIN);

  // Create servo control task
  xTaskCreate(servoTask, "ServoTask", 2048, NULL, 1, NULL);

  // Seed random number generator
  randomSeed(analogRead(0));
}

void loop() {
  if (!client.connected()) {
    Serial.println("Reconnecting to MQTT...");
    reconnect();
  }
  client.loop();

  // Publish sensor data
  String tof1_data = generateSensorData("env/tof1");
  client.publish(tof1_topic, tof1_data.c_str());
  if (tof1_position >= 0 && tof1_position < 4) {
    client.publish(tof1_pos_topics[tof1_position], tof1_data.c_str());
  }

  String tof2_data = generateSensorData("env/tof2");
  client.publish(tof2_topic, tof2_data.c_str());
  if (tof2_position >= 0 && tof2_position < 4) {
    client.publish(tof2_pos_topics[tof2_position], tof2_data.c_str());
  }

  String sw420_data = generateSensorData("env/sw420");
  client.publish(sw420_topic, sw420_data.c_str());
  if (sw420_scenario >= 0 && sw420_scenario < 6) {
    client.publish(sw420_scene_topics[sw420_scenario], sw420_data.c_str());
  }

  String env_infra_data = generateSensorData("env/env_infra");
  client.publish(env_infra_topic, env_infra_data.c_str());

  String dht_data = generateSensorData("env/dht");
  client.publish(dht_topic, dht_data.c_str());

  // Publish servo flags
  client.publish(servo_gate_topic, String(servo_gate).c_str());
  client.publish(servo_turn_topic, String(servo_turn).c_str());

  delay(1000); // Publish every 1 second
}

void reconnect() {
  int attempts = 0;
  while (!client.connected() && attempts < 5) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(mqtt_client_id)) {
      Serial.println("MQTT connected");
      // Subscribe to train_esp topics
      for (int i = 0; i < 4; i++) {
        client.subscribe(train_topics[i]);
      }
      // Subscribe to control topics
      for (int i = 0; i < 2; i++) {
        client.subscribe(control_topics[i]);
      }
    } else {
      Serial.print("Failed, rc=");
      Serial.print(client.state());
      Serial.println(" Trying again in 10 seconds");
      delay(10000);
      attempts++;
    }
  }
}

void callback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  if (strcmp(topic, "train/accelero") == 0) {
    train_accelero = message.toFloat();
  } else if (strcmp(topic, "train/ultra1") == 0) {
    train_ultra1 = message.toFloat();
  } else if (strcmp(topic, "train/ultra2") == 0) {
    train_ultra2 = message.toFloat();
  } else if (strcmp(topic, "train/power_on") == 0) {
    train_power_on = message.toInt();
  } else if (strcmp(topic, "control/env/servo_gate") == 0) {
    servo_gate = message.toInt();
  } else if (strcmp(topic, "control/env/servo_turn") == 0) {
    servo_turn = message.toInt();
  }
}

void servoTask(void *pvParameters) {
  while (1) {
    float env_infra = readEnvInfra();
    if (env_infra < servo_infra_threshold) {
      servo_gate = 1;
    }
    if (servo_gate == 1) {
      moveServoGate();
      servo_gate = 0;
    }
    if (servo_turn == 1) {
      moveServoTurn();
      servo_turn = 0;
    }
    vTaskDelay(100 / portTICK_PERIOD_MS); // Check every 100ms
  }
}

float readEnvInfra() {
  // Simulate sensor reading; replace with actual sensor code
  return random(0, 200);
}

void moveServoGate() {
  for (int pos = 0; pos <= 180; pos += 1) {
    servoGate.write(pos);
    delay(15);
  }
  for (int pos = 180; pos >= 0; pos -= 1) {
    servoGate.write(pos);
    delay(15);
  }
}

void moveServoTurn() {
  for (int pos = 0; pos <= 180; pos += 1) {
    servoTurn.write(pos);
    delay(15);
  }
  for (int pos = 180; pos >= 0; pos -= 1) {
    servoTurn.write(pos);
    delay(15);
  }
}

String generateSensorData(const char* topic) {
  if (strstr(topic, "tof1") != NULL || strstr(topic, "tof2") != NULL) {
    float value = random(0, 201); // 0 to 200 cm
    return String(value, 2);
  } else if (strstr(topic, "sw420") != NULL) {
    String bitString = "";
    for (int j = 0; j < 64; j++) {
      bitString += String(random(0, 2));
    }
    return bitString;
  } else if (strcmp(topic, "env/env_infra") == 0) {
    float value = random(0, 1001); // 0 to 1000
    return String(value, 2);
  } else if (strcmp(topic, "env/dht") == 0) {
    float value = random(150, 351) / 10.0; // 15.0 to 35.0 °C
    return String(value, 2);
  } else {
    return "0.0";
  }
}