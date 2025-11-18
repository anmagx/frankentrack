# Frankentrack

A hobbyist 5DOF headtracking solution written in python, utilizing an IMU like the MPU6500/6050. Supports single IR-LED tracking for X/Y translation.


## What is Frankentrack? 

Frankentrack is a headtracking solution for racing or flightsim games. It accepts motion sensor input over serial and sends them over UDP (opentrack-compatible). It also supports single brightspot tracking utilizing a webcam for providing X/Y translation. 

## Requirements

This example uses: 

* Arduino Nano 
* MPU6500


Single point IR tracking:
* Single IR LED (940nm)
* Resistor (150 Ohm)

But basically any way to get csv-structured IMU data from a serial port will do. 

CSV structure: 

time(millis),accelX,accelY,accelZ,gyroX,gyroY,gyroZ

A wide range of cameras are supported through pythons openCV-library. Including the PS3 Eye if you use this driver: 

""driver here""


## Roll / Pitch / Yaw Angles

The accelerometer and gyroscope readings are combined using a relatively simple complementary filter. Pitch and Roll are computed using the accelerometer values (with earth gravity being the reference point) plus the gyroscope for fast movements. As yaw angle can't depend on gravity for a true reference, these "simple" 6DOF sensors all introduce some sort of yaw drift over time. The program implements 2 procedures to deal with this: 


1. Calibration
   At startup, the sensor itself runs through a short calibration to discern accelerator and gyro offsets. The sensor should be still and level at this time. After the sensor data comes in, the first samples (add configuration reference here) are used to determine gyro drift. 

2. Drift Correction Angle
   You can set your preferred drift correction threshold angle. The sensor keeps track of it's starting position. When you look around, drift correction is minimal. When you look back to the direction of your starting position, and the pitch, roll and yaw angles are smaller than the drift correction angle threshold, drift correction takes over, and gradually returns the angles to 0. In practice, this means your view is recentered automatically whenever you look straight ahead, leading to stable headtracking even over long session lengths. 


There are lots of sensor fusion algorithms out there which aim to correct this yaw drift (e.g. Kalman, Madgwick, Mahony), but most of them rely on a 9DOF sensor package. In this case a magnetometer is included in the sensor to give a true north reference. This however also increases complexity quite a bit, as well as potential for failure. Magnetometers are tricky to calibrate precisely and magnetic interference is everywhere, especially on top of a headset, where the sensor sits. This rather simple solution works quite well for this use case.

## X / Y Movement

Adding a single IR-LED provides enough information to translate into X/Y-Movement. Theoretically, Z movement (towards/away from camera) could be determined from total brightness or visual light blob size, but I found this to be too sensitive to rotation - when you rotate the head, the angle from LED to camera changes, and so does total brightness as well as blob size. Adding a second LED and tracking the midpoint remedies this somewhat, but I did not get it to work in a satisfying manner, so the code does not support it for now. 


## ...Why? 

Professional IR tracking setups can be quite cost prohibitive. There are ample ways to build your own though, with most of them utilizing some variation of the delan clip: 3 IR LEDs, offset relative to each other, and an IR sensitive camera (like the PS3 Eye) tracking them. These are proven and have years of community experience behind them, so if you're looking for a reliable solution, you're probably quite well off with one of those. 

I personally just didn't like the way the clip was reaching into my field of view when wearing the headset. It feels bulky, which it needs to be: For precise movement recognition, you need some distance between those LEDs for the algorithm to be able to discern the angles clearly. 

This project is an attempt at achieve the same result, but in a smaller package: IMUs (Like the MPU6050/6500) are tiny and can deliver surprisingly accurate accelerometer and gyroscope readings, and quite fast too. The provided example utilizing an Arduino Nano with a MPU6500 easily gets to 120Hz, and could probably go even faster. 