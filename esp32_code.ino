#include <WiFi.h>
#include <WebServer.h>
#include <time.h>
#include <ZMPT101B.h>
#include <DHT.h>
#include <SPIFFS.h>

#define DHTPIN 26
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

const char* ssid = “your_wifi_name”;
const char* pswd = “your_wifi_password”;

const long gmtOffset = 19800;
const long daylightSaving = 0;

WebServer server(80);

const int sensorIn = 34;
int mVperAmp = 100;
int Watt = 0;
float kWh = 0;
float energy = 0;
double Voltage = 0;
double VRMS = 0;
double AmpsRMS = 0;
float v = 0;

#define VOLTAGE_PIN 32
#define SENSITIVITY 500.0f
#define VOLTAGE_CALIBRATION 1.136
ZMPT101B voltageSensor(VOLTAGE_PIN, 50.0);

#define MAX_SAMPLES 1440
float tempSamples[MAX_SAMPLES];
float humiditySamples[MAX_SAMPLES];
int sampleCount = 0;

String lastLog = “No log yet”;
int lastLoggedDay = -1;

void setup() {
Serial.begin(115200);
analogReadResolution(12);
voltageSensor.setSensitivity(SENSITIVITY);
dht.begin();

WiFi.begin(ssid, pswd);
while (WiFi.status() != WL_CONNECTED) {
delay(500);
Serial.print(”.”);
}
Serial.println(”\nWiFi connected: “);
Serial.println(WiFi.localIP());

if (!SPIFFS.begin(true)) {
Serial.println(“SPIFFS Mount Failed”);
return;
}

configTime(gmtOffset, daylightSaving, “pool.ntp.org”);

server.on(”/”, handleRoot);
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

  lastLog = String(dateStr) + "," +
            String(energy, 4) + "," +
            String(medianTemp, 2) + "," +
            String(medianHumidity, 2);

  File file = SPIFFS.open("/lastlog.txt", FILE_WRITE);
  if (file) {
    file.print(lastLog);
    file.close();
    Serial.println("\nDay Complete:");
    Serial.println(lastLog);
  } else {
    Serial.println("Failed to write log to SPIFFS");
  }

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
return (sorted[size/2 - 1] + sorted[size/2]) / 2.0;
else
return sorted[size/2];
}

void handleRoot() {
struct tm timeinfo;
getLocalTime(&timeinfo);
int currentHour = timeinfo.tm_hour;

if (currentHour == 23 && timeinfo.tm_min == 59 && timeinfo.tm_sec == 59) {
server.send(200, “text/plain”, lastLog);
} else {
File file = SPIFFS.open(”/lastlog.txt”);
if (file) {
String storedLog = file.readString();
file.close();
server.send(200, “text/plain”, storedLog);
} else {
server.send(200, “text/plain”, “No log available”);
}
}
}
