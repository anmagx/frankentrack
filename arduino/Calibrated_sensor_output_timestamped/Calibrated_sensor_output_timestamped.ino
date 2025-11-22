#include "FastIMU.h"
#include <Wire.h>

#define IMU_ADDRESS 0x68    //Change to the address of the IMU
#define PERFORM_CALIBRATION //Comment to disable startup calibration
MPU6500 IMU;               //Change to the name of any supported IMU! 
#define LED_PIN 3

// Based on FastIMU library (Install from arduino IDE)
// Currently supported IMUS: MPU9255 MPU9250 MPU6886 MPU6500 MPU6050 ICM20689 ICM20690 BMI055 BMX055 BMI160 LSM6DS3 LSM6DSL QMI8658

calData calib = { 0 };  //Calibration data
AccelData accelData;    //Sensor data
GyroData gyroData;

void setup() {
  Wire.begin();
  Wire.setClock(400000); //400khz clock
  Serial.begin(250000);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);  // LED on
  while (!Serial) {
    ;
  }

  int err = IMU.init(calib, IMU_ADDRESS);
  if (err != 0) {
    Serial.print("Error initializing IMU: ");
    Serial.println(err);
    while (true) {
      ;
    }
  }
  
#ifdef PERFORM_CALIBRATION
  Serial.println("FastIMU calibration & data example");
  Serial.println("Keep IMU level.");
  delay(2000);
  IMU.calibrateAccelGyro(&calib);
  Serial.println("Calibration done!");
  Serial.println("Accel biases X/Y/Z: ");
  Serial.print(calib.accelBias[0]);
  Serial.print(", ");
  Serial.print(calib.accelBias[1]);
  Serial.print(", ");
  Serial.println(calib.accelBias[2]);
  Serial.println("Gyro biases X/Y/Z: ");
  Serial.print(calib.gyroBias[0]);
  Serial.print(", ");
  Serial.print(calib.gyroBias[1]);
  Serial.print(", ");
  Serial.println(calib.gyroBias[2]);
  delay(1000);
  IMU.init(calib, IMU_ADDRESS);
#endif

  err = IMU.setGyroRange(250);      //USE THESE TO SET THE RANGE, IF AN INVALID RANGE IS SET IT WILL RETURN -1
  err = IMU.setAccelRange(2);       //THESE TWO SET THE GYRO RANGE TO ±500 DPS AND THE ACCELEROMETER RANGE TO ±2g
  
  if (err != 0) {
    Serial.print("Error Setting range: ");
    Serial.println(err);
    while (true) {
      ;
    }
  }
}

void loop() {
  static unsigned long startTime = millis();
  float timeSec = (millis() - startTime) / 1000.0;

  IMU.update();
  Serial.print(timeSec, 6);
  Serial.print(",");

  IMU.getAccel(&accelData);
  Serial.print(accelData.accelX, 6);
  Serial.print(",");
  Serial.print(accelData.accelY, 6);
  Serial.print(",");
  Serial.print(accelData.accelZ, 6);
  Serial.print(",");

  IMU.getGyro(&gyroData);
  Serial.print(gyroData.gyroX, 6);
  Serial.print(",");
  Serial.print(gyroData.gyroY, 6);
  Serial.print(",");
  Serial.print(gyroData.gyroZ, 6);

  Serial.println();

  delay(2); //~120hz
}
