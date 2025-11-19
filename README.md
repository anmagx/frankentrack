# Frankentrack

OpenTrack-Compatible UDP sender for 3DOF (Yaw/Pitch/Roll) headtracking, utilizing IMU data sensor fusion. Written in Python. 
Optional single-point IR-LED tracking feature for X/Y movement estimation. 

## What is Frankentrack? 

Frankentrack is the product of unholy combination of IMU sensor data fusion and (optional) single-point IR-LED tracking to achieve a stable, responsive, precise, lightweight and cost effective 5DOF headtracking solution with a smaller physical footprint than traditional 3-point trackers.

## Features

### GUI Features
* Modular tkinter GUI with error handling and logging functions
* Python multiprocessing using independent queues for IPC
* Serial reader with debounced output
* Message panel for printing debug messages
* Metrics (Serial msgs/s, sent Items/s, camera FPS)

### Code structure
* Central configuration file for runtime constants
* Central configuration file for user preferences (loaded at startup)

### Functional Features
* Performs Sensor fusion with complementary filter to compute euler angles (Yaw/Pitch/Roll) from accelerometer and gyroscope data
* Constant drift correction, automatic recentering
* Optional: Single-point IR-LED tracking using a webcam to compute X/Y position

## Installation
* Clone repository
* `python -m pip install requirements.txt`

## Requirements

**Software**

Python
* OpenCV
* pyserial
* tkinter

**Hardware**

Basically anything that will give you csv-structured data over a serial port will work. The outlined example assumes an Arduino Nano (connected via USB-C) and an MPU6500 IMU communicating over Serial at 250000 Baud. 

Required data structure:

`time(millis),accX,accY,accZ,gyrX,gyrY,gyrZ`

## Frequently asked Questions (FAQ)

### Why?

Professional IR tracking setups can be quite cost prohibitive. There are ample ways to build your own though, with most of them utilizing some variation of the delan clip: 3 IR LEDs, offset relative to each other, and an IR sensitive camera (like the PS3 Eye) tracking them. These are proven and have years of community experience behind them, so if you're looking for a reliable solution, you're probably quite well off with one of those.

I personally just didn't like the way the clip was reaching into my field of view when wearing the headset. It feels bulky, which it needs to be: For precise movement recognition, you need some distance between those LEDs for the algorithm to be able to discern the angles clearly.

This project is an attempt at achieve the same result, but in a smaller package: IMUs (Like the MPU6050/6500) are tiny and can deliver surprisingly accurate accelerometer and gyroscope readings, and quite fast too. The provided example utilizing an Arduino Nano with a MPU6500 easily gets to 120Hz, and could probably go even faster.

### How are the orientation angles computed?

The yaw, pitch and roll angles are computed from accelerometer and gyroscope data using a comparatively simple complementary filter. Pitch and Roll are computed using the accelerometer values (with earth gravity being the reference point) plus the gyroscope for fast movements. Yaw is computed using gyroscope only, as we can't infer a true reference using gravity. As a consequence of this, yaw angle will drift over time. The program implements 2 corrections for this: 

1. **Calibration**

    At Startup, the sensor itself runs through a short calibration to discern accelerator and gyro offsets. The sensor should be kept **still and level** during this time. After the sensor data comes in, the first samples (Number of calibration samples is configurable) are captured and used to calculate and offset Yaw drift. 

2. **Conditional Drift correction using threshold angle**

     You can set your preferred drift correction threshold angle. The sensor keeps track of it's starting position. When you look around, drift correction is minimal. When you look back to the direction of your starting position, and the pitch, roll and yaw angles are smaller than the drift correction angle threshold, drift correction takes over, and gradually returns the angles to 0. In practice, this means your view is recentered automatically whenever you look straight ahead, leading to stable headtracking even over long session lengths.

There are lots of sensor fusion algorithms out there which aim to correct this yaw drift (e.g. Kalman, Madgwick, Mahony), but most of them rely on a 9DOF sensor package. In this case a magnetometer is included in the sensor to give a true north reference using earths magnetic field. This however also increases complexity quite a bit, as well as potential for failure. Magnetometers are tricky to calibrate precisely and magnetic interference is everywhere, especially on top of a headset, where the sensor sits. This rather simple solution works quite well for this use case.

### How are X/Y positions calculated? 

As an optional feature, a simple single-point IR-LED tracking system is implemented. Using python-opencv, a wide range of cameras are supported, including the infamous PS3 Eye if you use the official driver. (Installation instructions linked here)

The camera tracks the LED point across the screen and estimates your movements to send to OpenTrack along with the orientation angles. 

### Why no Z-Movement? 

Z movement is tricky to implement using a single LED. While there are methods (blob size change detection or tracking of total LED brightness) these are quite prone to behave in an inconsistent manner as a result of the LED itself rotating. 

Rotating your head (to look at something) rotates the LED, the angle to the camera changes, and with it, light intensity. This causes head rotation to produce unwanted movement detections. 

Adding a second LED and tracking the midpoint between the two can somewhat remedy this. However, I did not get it to work in a satisfying and reliable manner, so the code doesn't support it for now. 

### How does it functionally compare to a traditional 3-point tracking solution? 

Just from my experience, using completely self-built tracking hardware, there are some considerations and tradeoffs. 

**Responsiveness**

With Frankentrack, you're pretty much only limited by the number of sensor readings you can achieve per second, which can easily go into the hundreds - while with a more traditional 3-point tracking, your bottleneck will be the camera (framerate/inherent latency introduced by image processing/compression). With some careful calibration, you can get an incredibly responsive system. My example runs at about 120Hz. 

**Precision**

In 3-point tracking, the precision of your solution hinges on the construction of your LED-clip. Wider distances between the LEDs offer more precise measurements, but increase overall package size and bulkiness. Also, since you tend to wear the clip on either the left or the right side, rotations may be more consistent in one direction than the other. 

Frankentrack is equally stable in each movement direction. The yaw drift is barely noticeable and blends in with the natural inconsistencies introduced by human movement. It is also recentered gradually each time you look straight ahead, leading to long term stability. 

**Consistency**

With 3-point tracking, I found that some orientations are quite tricky to hold - for example, looking down and moving around the yaw axis always tended to introduce some "wobble" which I couldn't quite get to go away. 

Using IMU angles, there are no angles that are more or less stable than others.

**Tradeoffs**

Very fast movements can trip up the internal state of the sensor, leading to a desync of what the sensor expects it's starting position to be and what it actually is. This requires manual recentering, which can be done by the press of a button. 

In practice during normal play, I didn't have this happen very often. 
