# Acceltrack

A hobbyist 5DOF headtracking solution written in python, utilizing an IMU like the MPU6500/6050. Supports single IR-LED tracking for X/Y translation.


## What is Acceltrack? 

Acceltrack is a headtracking solution for racing or flightsim games. It accepts motion sensor input over serial and sends them over UDP (opentrack-compatible). It also supports single brightspot tracking utilizing a webcam for providing X/Y translation. 

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


## ...why? 

Professional IR tracking setups can be quite cost prohibitive. There are ample ways to build your own though, with most of them utilizing some variation of the delan clip: 3 IR LEDs, offset relative to each other, and an IR sensitive camera (like the PS3 Eye) tracking them. These are proven and have years of community experience behind them, so if you're looking for a reliable solution, you're probably quite well off with one of those. 

I personally just didn't like the way the clip was reaching into my field of view when wearing the headset. It feels bulky, which it needs to be: For precise movement recognition, you need some distance between those LEDs for the algorithm to be able to discern the angles clearly. 

This project is an attempt at achieve the same result, but in a smaller package: IMUs (Like the MPU6050/6500) are tiny and 