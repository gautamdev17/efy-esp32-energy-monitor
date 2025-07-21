#include <WiFi.h>
#include <WebServer.h>
#include <time.h>
#include <ZMPT101B.h>
#include <DHT.h>
#include <FS.h>
#include <SPIFFS.h>

#define DHTPIN 27
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

// wifi
const char* ssid = “wifi_name”;
const char* pswd = “wifi_password”;

// ntp
const long gmtOffset = 19800;
const long daylightSaving = 0;

WebServer server(80);

// sensors
#define VOLTAGE_PIN 32
#define SENSITIVITY 500.0f
#define VOLTAGE_CALIBRATION 1.136
ZMPT101B voltageSensor(VOLTAGE_PIN, 50.0);

const int sensorIn = 34;
int mVperAmp = 100;

float v = 0;
int Watt = 0;
float kWh = 0;
float energy = 0;
double Voltage = 0;
double VRMS = 0;
double AmpsRMS = 0;

// Temp/Humidity samples
#define MAX_SAMPLES 1440
float tempSamples[MAX_SAMPLES];
float humiditySamples[MAX_SAMPLES];
int sampleCount = 0;

int lastLoggedDay = -1;

void setup() {
Serial.begin(115200);
analogReadResolution(12);
voltageSensor.setSensitivity(SENSITIVITY);
dht.begin();

if (!SPIFFS.begin(true)) {
Serial.println(“SPIFFS Mount Failed”);
return;
}

WiFi.begin(ssid, pswd);
while (WiFi.status() != WL_CONNECTED) {
delay(500);
Serial.print(”.”);
}

Serial.println(”\nWiFi connected: “);
Serial.println(WiFi.localIP());

configTime(gmtOffset, daylightSaving, “pool.ntp.org”);

server.on(”/”, handleRoot);
server.on(”/monthly”, handleMonthly);  // NEW ENDPOINT
server.begin();
Serial.println(“HTTP server started”);
}

void loop() {
server.handleClient();

Voltage = getVPP();
VRMS = (Voltage / 2.0) * 0.707;
AmpsRMS = (VRMS * 1000) / mVperAmp;
Watt = (AmpsRMS * 240 / 1.3);
kWh = (Watt / 1000.0) * (10.0 / 3600.0);
energy += kWh;

if (sampleCount < MAX_SAMPLES) {
float t = dht.readTemperature();
float h = dht.readHumidity();
if (!isnan(t) && !isnan(h)) {
tempSamples[sampleCount] = t;
humiditySamples[sampleCount] = h;
sampleCount++;
}
}

struct tm timeinfo;
if (getLocalTime(&timeinfo)) {
int currentHour = timeinfo.tm_hour;
int currentMinute = timeinfo.tm_min;
int currentSecond = timeinfo.tm_sec;
int currentDay = timeinfo.tm_mday;

if (currentHour == 23 && currentMinute == 59 && currentSecond == 59 && currentDay != lastLoggedDay) {
  char dateStr[20];
  strftime(dateStr, sizeof(dateStr), "%d/%m/%Y", &timeinfo);

  float medianTemp = calculateMedian(tempSamples, sampleCount);
  float medianHumidity = calculateMedian(humiditySamples, sampleCount);

  String log = String(dateStr) + "," +
               String(energy, 2) + "," +
               String(medianTemp, 2) + "," +
               String(medianHumidity, 2);

  File file = SPIFFS.open("/monthlog.txt", FILE_APPEND);
  if (file) {
    file.println(log);
    file.close();
  }

  Serial.println("\nDay Logged:");
  Serial.println(log);

  energy = 0;
  sampleCount = 0;
  lastLoggedDay = currentDay;
}

}

delay(10);
}

float getVPP() {
float result;
int readValue;
int maxValue = 0;
int minValue = 4095;
v = 0;
int c = 0;

uint32_t start_time = millis();
while ((millis() - start_time) < 10000) {
v += voltageSensor.getRmsVoltage() * VOLTAGE_CALIBRATION;
c++;
readValue = analogRead(sensorIn);
if (readValue > maxValue) maxValue = readValue;
if (readValue < minValue) minValue = readValue;
}
v /= c;
result = ((maxValue - minValue) * 3.3) / 4095.0;
return result;
}

float calculateMedian(float* arr, int size) {
if (size == 0) return 0;
float sorted[size];
memcpy(sorted, arr, sizeof(float) * size);
std::sort(sorted, sorted + size);
if (size % 2 == 0)
return (sorted[size / 2 - 1] + sorted[size / 2]) / 2.0;
else
return sorted[size / 2];
}

void handleRoot() {
String live = String(energy, 4) + “,” +
String(sampleCount > 0 ? tempSamples[sampleCount - 1] : 0, 2) + “,” +
String(sampleCount > 0 ? humiditySamples[sampleCount - 1] : 0, 2);
server.send(200, “text/plain”, live);
}

void handleMonthly() {
if (SPIFFS.exists(”/monthlog.txt”)) {
File file = SPIFFS.open(”/monthlog.txt”);
String content = file.readString();
file.close();
server.send(200, “text/plain”, content);
} else {
server.send(200, “text/plain”, “No logs available”);
}
}
