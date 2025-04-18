#include <WiFi.h>
#include <PubSubClient.h>

// WiFi credentials
const char* ssid = "Doraemon";
const char* password = "helicopter";

// MQTT Broker settings
const char* mqtt_server = "192.168.244.143";
const int mqtt_port = 1883;
const char* mqtt_client_id = "train_esp";

// Topics for train_esp
const char* accelero_topic = "train/accelero";
const char* ultra1_topic = "train/ultra1";
const char* ultra2_topic = "train/ultra2";
const char* power_on_topic = "train/power_on";

// Subscribed topics from env_esp and control
const char* env_topics[] = {
  "env/tof1", "env/tof1_pos1", "env/tof1_pos2", "env/tof1_pos3", "env/tof1_pos4",
  "env/tof2", "env/tof2_pos1", "env/tof2_pos2", "env/tof2_pos3", "env/tof2_pos4",
  "env/sw420", "env/sw420_scene1", "env/sw420_scene2", "env/sw420_scene3", "env/sw420_scene4", "env/sw420_scene5", "env/sw420_scene6",
  "env/env_infra", "env/dht", "env/servo_gate", "env/servo_turn"
};
const char* control_topic = "control/train/power_on";

// Global variables for received data from env_esp
float env_tof1 = 0.0;
float env_tof1_pos1 = 0.0;
float env_tof1_pos2 = 0.0;
float env_tof1_pos3 = 0.0;
float env_tof1_pos4 = 0.0;
float env_tof2 = 0.0;
float env_tof2_pos1 = 0.0;
float env_tof2_pos2 = 0.0;
float env_tof2_pos3 = 0.0;
float env_tof2_pos4 = 0.0;
String env_sw420 = "";
String env_sw420_scene1 = "";
String env_sw420_scene2 = "";
String env_sw420_scene3 = "";
String env_sw420_scene4 = "";
String env_sw420_scene5 = "";
String env_sw420_scene6 = "";
float env_infra = 0.0;
float env_dht = 0.0;
int env_servo_gate = 0;
int env_servo_turn = 0;

// Power flag
int power_on = 0;

// WiFi and MQTT clients
WiFiClient espClient;
PubSubClient client(espClient);

// Function prototypes
void reconnect();
void callback(char* topic, byte* payload, unsigned int length);
void powerOnTask(void *pvParameters);
String generateSensorData(const char* topic);

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

  // Create power_on task
  xTaskCreate(powerOnTask, "PowerOnTask", 2048, NULL, 1, NULL);

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
  String accelero_data = generateSensorData("train/accelero");
  client.publish(accelero_topic, accelero_data.c_str());

  String ultra1_data = generateSensorData("train/ultra1");
  client.publish(ultra1_topic, ultra1_data.c_str());

  String ultra2_data = generateSensorData("train/ultra2");
  client.publish(ultra2_topic, ultra2_data.c_str());

  // Publish power_on flag
  client.publish(power_on_topic, String(power_on).c_str());

  delay(1000); // Publish every 1 second
}

void reconnect() {
  int attempts = 0;
  while (!client.connected() && attempts < 5) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(mqtt_client_id)) {
      Serial.println("MQTT connected");
      // Subscribe to env_esp topics
      for (int i = 0; i < sizeof(env_topics) / sizeof(env_topics[0]); i++) {
        client.subscribe(env_topics[i]);
      }
      // Subscribe to control topic
      client.subscribe(control_topic);
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
  if (strcmp(topic, "env/tof1") == 0) env_tof1 = message.toFloat();
  else if (strcmp(topic, "env/tof1_pos1") == 0) env_tof1_pos1 = message.toFloat();
  else if (strcmp(topic, "env/tof1_pos2") == 0) env_tof1_pos2 = message.toFloat();
  else if (strcmp(topic, "env/tof1_pos3") == 0) env_tof1_pos3 = message.toFloat();
  else if (strcmp(topic, "env/tof1_pos4") == 0) env_tof1_pos4 = message.toFloat();
  else if (strcmp(topic, "env/tof2") == 0) env_tof2 = message.toFloat();
  else if (strcmp(topic, "env/tof2_pos1") == 0) env_tof2_pos1 = message.toFloat();
  else if (strcmp(topic, "env/tof2_pos2") == 0) env_tof2_pos2 = message.toFloat();
  else if (strcmp(topic, "env/tof2_pos3") == 0) env_tof2_pos3 = message.toFloat();
  else if (strcmp(topic, "env/tof2_pos4") == 0) env_tof2_pos4 = message.toFloat();
  else if (strcmp(topic, "env/sw420") == 0) env_sw420 = message;
  else if (strcmp(topic, "env/sw420_scene1") == 0) env_sw420_scene1 = message;
  else if (strcmp(topic, "env/sw420_scene2") == 0) env_sw420_scene2 = message;
  else if (strcmp(topic, "env/sw420_scene3") == 0) env_sw420_scene3 = message;
  else if (strcmp(topic, "env/sw420_scene4") == 0) env_sw420_scene4 = message;
  else if (strcmp(topic, "env/sw420_scene5") == 0) env_sw420_scene5 = message;
  else if (strcmp(topic, "env/sw420_scene6") == 0) env_sw420_scene6 = message;
  else if (strcmp(topic, "env/env_infra") == 0) env_infra = message.toFloat();
  else if (strcmp(topic, "env/dht") == 0) env_dht = message.toFloat();
  else if (strcmp(topic, "env/servo_gate") == 0) env_servo_gate = message.toInt();
  else if (strcmp(topic, "env/servo_turn") == 0) env_servo_turn = message.toInt();
  else if (strcmp(topic, "control/train/power_on") == 0) power_on = message.toInt();
}

void powerOnTask(void *pvParameters) {
  while (1) {
    if (power_on == 1) {
      // Action for power_on; placeholder for now
      power_on = 0;
    }
    vTaskDelay(100 / portTICK_PERIOD_MS); // Check every 100ms
  }
}

String generateSensorData(const char* topic) {
  if (strcmp(topic, "train/accelero") == 0) {
    float value = random(0, 100) / 10.0; // 0.0 to 10.0 g
    return String(value, 2);
  } else if (strcmp(topic, "train/ultra1") == 0 || strcmp(topic, "train/ultra2") == 0) {
    float value = random(20, 401); // 20 to 400 cm
    return String(value, 2);
  } else {
    return "0.0";
  }
}