# Mouth-Operated Mouse V3

An open-source, affordable assistive technology project that enables computer control through mouth movements and sip/puff actions. This is an updated version of the original Mouth-Operated Mouse, now utilizing an Arduino Leonardo for direct HID (Human Interface Device) emulation and an enhanced Python application for calibration and training.

## Overview

This project creates a mouth-operated mouse combining a pressure sensor for sip/puff actions with a joystick for cursor movement, allowing users with limited hand mobility to control a computer. A keyboard mode is also included, where 2 to 8 keybinds are assigned to different angles, and special keys can be binded to sips and puffs. The device functions as follows:

*   **Joystick**: Controls cursor movement (operated by mouth)
*   **Sip/Puff Actions**:
    *   Hard sip → Right click
    *   Soft sip → Scroll down
    *   Neutral → No action
    *   Soft puff → Scroll up
    *   Hard puff → Left click

## Key Features of V3

*   **Arduino Leonardo Integration**: Direct USB HID emulation, eliminating the need for a separate Python script for mouse control on the computer side. The Arduino Leonardo can act directly as a mouse.
*   **Enhanced Python Application (`App.py`)**: A comprehensive GUI application built with `customtkinter` for:
    *   **Tuning & Profiles**: Adjust pressure thresholds and joystick sensitivity, save and load custom profiles.
    *   **Trainer**: Interactive exercises to improve sip/puff and joystick control accuracy.
    *   **Calibrate Sensor**: Visualize real-time pressure data and assist in setting optimal thresholds.
    *   **Stick Control**: Visual representation of joystick input and deadzone.

*   **Improved Responsiveness**: Direct HID communication from Arduino Leonardo offers lower latency.
*   **Modular Design**: Easy customization and integration of components.

## Components

1.  **Arduino pro micro** (~$1.53 AUD)
    *   Replaces Arduino Uno and Leonardo for direct HID capabilities and a more compact design.
2.  **NPA-300B-001G (Most NPA pressure sensor models will work)** (~$2.8 to 54 AUD)
    *    - Specifically designed for sip/puff applications
         - Note that most models operated imilarly, meaning that there is no point in buying the more expensive models of the NPA sensors
3.  **Joystick Module**
    *   Analog Thumb Joystick Module (~$0.35 AUD)
4.  **Tubing and Mouthpiece:**
    *   Food-grade silicone tubing 1 meter - 2mm x 3mm (~$1.39 AUD) 
5.  **3d Printed parts**
    *   Mouthpeice, Casing, and arm (Cost varies, but estimated around 35 AUD)
5.  **Soldering Components:**
    *   3cm x 7cm proto board (~$0.14 AUD)
    *   Basic soldering stuff, wires, solder, flux (Cost varies, estimated around 2 to 3 AUD for me)
    *   USB to USB-C cable for Arduino (~$0.73 AUD)
    *   1 micro farad capacitor (~$0.16 AUD)
    *   DIP14 PCB Adapter Plate (~$0.55 AUD)
    
**Estimated Total Cost:** Approximately $45 AUD not including shipping, cost varies from country to country

## Setup Instructions

### 1. Hardware Assembly

Follow these basic instructions:

*   **Pressure Sensor (NPA-300B-001G) Connections:**
    *   VSS/Pin 6  → Arduino GND and VDD/Pin 9 through a 1 microfarad capacitor
    *   VDD/Pin 9  → Arduino +2.7 to +5.5V
    *   SIG/Pin 8 → Arduino A0
*   **Joystick Module Connections:**
    *   GND pin → Arduino GND 
    *   +5V pin → Arduino 5V (Connect with the Pressure sensor VDD/Pin 9 connection)
    *   VRx (X-axis) → Arduino A1
    *   VRy (Y-axis) → Arduino A2
    *   SW (Switch, optional) → Not used, but can be connected to a digital pin if desired
*   **Tubing Connection:**
    *   Connect silicon food-grade tubing to the pressure port on the sensor, there are 2 pressure ports for most models, the one further away from the dot in the corner should be the one you connect to, the other one inverts sips and puffs
    *   Thread your tubing through the hole on top of the casing
    *   Connect your mouthpiece to the joystick shaft
    *   The other end of the tubing connects to the hole on the mouthpiece, make sure the hole on the mouthpeice is facing upwards
*   **Casing** 
    *   Make sure everything works first, and that the joystick has enough angle of movement
    *   Assemble the 3d printed arm/stand (link at the bottom of this file) with the final screw connecting the casing with the 3d printed arm/stand
    *   Once everything works, connect your cable to the arduino, and slide the cover over the open side of the casing

*   **Tips and advices**
    *   Depending on your 3d printer settings, some of the components might not fit, simply sand down the parts that are too big or too tight, such as the thin part of the sliding cover, or the screw and screw hole, DO NOT SAND DOWN yOUR MOUTHPEICE, you do not want to breathe in the fiament dust, if the hole does not fit on the hatch, you can use a small screwdriver and apply force to the hole and expand it a bit.
    *   Some model of the sensors, such as the one used for this project (NPA-300B-001G) has an uneven pressure detection range, meaning that it can detect stronger puffs and weaker sips, this can cause the sips to be very sensitive, so much so that it is very difficult to control the soft and hard sips, to fix this, simple poke a few holes in the tubing
    *   Remember to connect capacitor with correct polarity if you are using an electrolytic capacitor

### 2. Arduino IDE Setup

1.  **Install Arduino IDE**: Download and install the Arduino IDE from the [official website](https://www.arduino.cc/en/software).
2.  **Install Arduino Pro Micro Board**: Go to `Tools > Board > Boards Manager...` and search for "Arduino AVR Boards". Install the package that includes the Arduino Leonardo.
3.  **Install Libraries**: The `V3.ino` sketch uses the built-in `Mouse.h` library. No additional library installations are required for the Arduino sketch.
4.  **Upload Sketch**: Open `V3.ino` in the Arduino IDE, select `Tools > Board > Arduino Pro Micro`, and choose the correct `Port`. Then, click `Upload`.

### 3. Python Application Setup

1.  **Install Python**: Ensure you have Python 3.x installed. You can download it from [python.org](https://www.python.org/downloads/).
2.  **Install Dependencies**: Open a terminal or command prompt and navigate to the directory where `App.py` is located. Install the required Python libraries using pip:
    ```bash
    pip install pyserial customtkinter pyautogui
    ```
3.  **Run Application**: Execute the Python application:
    ```bash
    python App.py
    ```

## Usage

Once the Arduino sketch is uploaded and the Python application is running, you can use the `App.py` interface to:

*   **Connect to Arduino**: Select the serial port connected to your Arduino Leonardo and click "Connect".
*   **Tune Parameters**: Adjust the pressure thresholds (Hard Sip, Neutral Min/Max, Soft Puff, Hard Puff) and joystick deadzone/cursor speed. Apply settings to the Arduino.
*   **Calibrate Sensor**: Use the "Calibrate Sensor" tab to visualize real-time pressure readings and fine-tune your thresholds for optimal performance.
*   **Train**: Utilize the "Trainer" tab to practice and improve your control.
*   **Manage Profiles**: Save and load different configurations as profiles.

## Troubleshooting

*   **Arduino Not Detected**: Ensure the Arduino Pro Micro drivers are correctly installed and the correct port is selected in the Arduino IDE and `App.py`.
*   **Serial Communication Issues**: Verify that no other application is using the serial port. Restarting the Arduino IDE or `App.py` might help.
*   **Mouse Not Moving/Clicking**: Check the pressure sensor and joystick connections. Ensure the `V3.ino` sketch is successfully uploaded to the Arduino Leonardo.
*   **Calibration**: The pressure thresholds are highly dependent on your specific sensor and lung capacity. Use the "Calibrate Sensor" tab in `App.py` to find your optimal settings.

## Link for 3d printed arm/stand: https://www.printables.com/model/647794-flexible-sturdy-phone-arm-100-printed/files

*  **There is no need to print the CZFA_FlexFrame_PhoneMount.stl, as that is a phone stand, instead, you are connecting the screw that was suppose to join the phone holder and the arm/stand to the casing instead

## Link for video guides:

* Hardware: https://youtu.be/UBpAdc31Nfw
* Software: https://youtu.be/A-l-xfMGubU

## 🛠️ OSHWA Certification

This hardware project is certified by the [Open Source Hardware Association (OSHWA)](https://www.oshwa.org/).

**Certification UID**: [AU000021](https://certification.oshwa.org/au000021.html)
## Contributing

Contributions are welcome! Please feel free to fork the repository, make improvements, and submit pull requests. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is open-source and available under the [MIT License](https://opensource.org/licenses/MIT).
