// =================================================================
// Integrated Hybrid Controller Sketch - FINAL & COMPLETE
// =================================================================

#include <Mouse.h>
#include <Keyboard.h>
#include <math.h>

// --- Pin Definitions ---
const int PRESSURE_PIN = A0;
const int JOY_X_PIN = A1;
const int JOY_Y_PIN = A2;

// --- Operating Modes ---
#define MODE_MOUSE 0
#define MODE_KEYBOARD 1
byte currentMode = MODE_MOUSE;

// --- State Flags ---
bool isLeftPressed_mouse = false;
bool isRightPressed_mouse = false;
bool isHardSipKeyHeld_kbd = false;
bool isSoftSipKeyHeld_kbd = false;
bool isSoftPuffKeyHeld_kbd = false;
bool isHardPuffKeyHeld_kbd = false;
int last_pressed_joy_key_index = -1;

// --- Parameters (Set by the Python GUI) ---
int hardSipThreshold = -200;
int neutralMin = -100;
int neutralMax = 25;
int softPuffThreshold = 100;
int hardPuffThreshold = 200;
int joystickDeadzone = 20;
int joystickMovementThreshold = 10;
int cursorSpeed = 10;
int softActionDelay = 150;

int sipSensitivity = 100;
int puffSensitivity = 100;

// --- CUSTOMIZABLE KEYBOARD VARS ---
int num_joy_sections = 8;
// *** NEW: Store two keys per sector ***
byte joy_keybinds[16][2]; // [sector_index][key_index: 0 or 1]
byte key_hpt = 'f';
byte key_spt = 'r';
byte key_hst = 'e';
byte key_sst = 'q';

// --- Timing, Sampling & Calibration ---
unsigned long sampleTimer = 0;
const int SAMPLE_PERIOD_MS = 5;
const int SAMPLE_LENGTH = 10;
int pressureSamples[SAMPLE_LENGTH];
int sampleCounter = 0;
unsigned long inputUpdateTimer = 0;
const int INPUT_UPDATE_PERIOD_MS = 15;
bool calibrationModeActive = false;
unsigned long lastCalibSendTime = 0;
int joyXCenter, joyYCenter;
int pressureCenter;

void setup() {
  Serial.begin(115200);

  Mouse.begin();
  Keyboard.begin();
  
  delay(1000); 
  
  long pressureSum = 0;
  for (int i = 0; i < 32; i++) {
    pressureSum += analogRead(PRESSURE_PIN);
    delay(10); 
  }
  pressureCenter = pressureSum / 32;
  
  joyXCenter = analogRead(JOY_X_PIN);
  joyYCenter = analogRead(JOY_Y_PIN);
  
  // Set default keybinds (now with two keys)
  char default_keys[8][2] = {{'d', ' '}, {'d', 's'}, {'s', ' '}, {'a', 's'}, {'a', ' '}, {'a', 'w'}, {'w', ' '}, {'w', 'd'}};
  for(int i = 0; i < 8; i++){
    joy_keybinds[i][0] = default_keys[i][0];
    joy_keybinds[i][1] = default_keys[i][1];
  }
  
  releaseAllInputs();
  Serial.print("INFO:Calibrated Pressure Center: ");
  Serial.println(pressureCenter);
  Serial.println("INFO:Controller Ready. Default Mode: Mouse");
}

void loop() {
  handleSerialCommands();

  if (calibrationModeActive) {
    if (millis() - lastCalibSendTime >= 50) {
      int raw_pressure = analogRead(PRESSURE_PIN) - pressureCenter;
      int scaled_pressure;
      if (raw_pressure < 0) {
        scaled_pressure = (long)raw_pressure * sipSensitivity / 100;
      } else {
        scaled_pressure = (long)raw_pressure * puffSensitivity / 100;
      }
      Serial.print("CALIB_P:");
      Serial.println(scaled_pressure);
      lastCalibSendTime = millis();
    }
    return;
  }

  if (millis() - sampleTimer >= SAMPLE_PERIOD_MS) {
    samplePressure();
    sampleTimer = millis();
  }
  
  if (currentMode == MODE_MOUSE) {
    if (sampleCounter >= SAMPLE_LENGTH) {
      int avgPressure = calculateAveragePressure();
      Serial.print("P:"); Serial.println(avgPressure);
      processPressureMouse(avgPressure);
      sampleCounter = 0; 
    }
    if (millis() - inputUpdateTimer >= INPUT_UPDATE_PERIOD_MS) {
      updateMouseJoystick();
      inputUpdateTimer = millis();
    }
  } else if (currentMode == MODE_KEYBOARD) {
    if (sampleCounter >= SAMPLE_LENGTH) {
      int avgPressure = calculateAveragePressure();
      Serial.print("P:"); Serial.println(avgPressure);
      processPressureKeyboard(avgPressure);
      sampleCounter = 0;
    }
    if (millis() - inputUpdateTimer >= INPUT_UPDATE_PERIOD_MS) {
      updateKeyboardJoystick();
      inputUpdateTimer = millis();
    }
  }
}

// =================================================================
// SENSOR & INPUT PROCESSING
// =================================================================
void samplePressure() {
  if (sampleCounter < SAMPLE_LENGTH) {
    int raw_centered_pressure = analogRead(PRESSURE_PIN) - pressureCenter;
    
    int scaled_pressure;
    if (raw_centered_pressure < 0) {
      scaled_pressure = (long)raw_centered_pressure * sipSensitivity / 100;
    } else {
      scaled_pressure = (long)raw_centered_pressure * puffSensitivity / 100;
    }
    
    pressureSamples[sampleCounter] = scaled_pressure;
    sampleCounter++;
  }
}

int calculateAveragePressure() {
  long sum = 0;
  for (int i = 0; i < SAMPLE_LENGTH; i++) sum += pressureSamples[i];
  return sum / SAMPLE_LENGTH;
}

void processPressureMouse(int pressure) {
  if (pressure >= hardPuffThreshold) { if (!isLeftPressed_mouse) { Mouse.press(MOUSE_LEFT); isLeftPressed_mouse = true; } } 
  else { if (isLeftPressed_mouse) { Mouse.release(MOUSE_LEFT); isLeftPressed_mouse = false; } }
  
  if (pressure <= hardSipThreshold) { if (!isRightPressed_mouse) { Mouse.press(MOUSE_RIGHT); isRightPressed_mouse = true; } }
  else { if (isRightPressed_mouse) { Mouse.release(MOUSE_RIGHT); isRightPressed_mouse = false; } }

  if (pressure >= softPuffThreshold && pressure < hardPuffThreshold) { Mouse.move(0, 0, 1); } 
  else if (pressure <= neutralMin && pressure > hardSipThreshold) { Mouse.move(0, 0, -1); }
}

void processPressureKeyboard(int pressure) {
  if (pressure >= hardPuffThreshold) { if (!isHardPuffKeyHeld_kbd) { Keyboard.press(key_hpt); isHardPuffKeyHeld_kbd = true; } } 
  else { if (isHardPuffKeyHeld_kbd) { Keyboard.release(key_hpt); isHardPuffKeyHeld_kbd = false; } }
  
  if (pressure >= softPuffThreshold && pressure < hardPuffThreshold) { if (!isSoftPuffKeyHeld_kbd) { Keyboard.press(key_spt); isSoftPuffKeyHeld_kbd = true; } }
  else { if (isSoftPuffKeyHeld_kbd) { Keyboard.release(key_spt); isSoftPuffKeyHeld_kbd = false; } }

  if (pressure <= hardSipThreshold) { if (!isHardSipKeyHeld_kbd) { Keyboard.press(key_hst); isHardSipKeyHeld_kbd = true; } }
  else { if (isHardSipKeyHeld_kbd) { Keyboard.release(key_hst); isHardSipKeyHeld_kbd = false; } }
  
  if (pressure <= neutralMin && pressure > hardSipThreshold) { if (!isSoftSipKeyHeld_kbd) { Keyboard.press(key_sst); isSoftSipKeyHeld_kbd = true; } }
  else { if (isSoftSipKeyHeld_kbd) { Keyboard.release(key_sst); isSoftSipKeyHeld_kbd = false; } }
}

void updateKeyboardJoystick() {
  int joyX = analogRead(JOY_X_PIN) - joyXCenter;
  int joyY = analogRead(JOY_Y_PIN) - joyYCenter;
  Serial.print("JOY:"); Serial.print(joyX); Serial.print(","); Serial.println(joyY);

  float magnitude = sqrt(pow(joyX, 2) + pow(joyY, 2));
  int current_section_index = -1;
  
  if ((magnitude / 512.0) * 100.0 > joystickMovementThreshold) {
      float slice_angle = 360.0 / num_joy_sections;
      float angle = atan2((float)-joyY, (float)joyX) * 180.0 / PI; 
      
      angle += slice_angle / 2.0;
      if (angle < 0) { angle += 360.0; }
      if (angle >= 360.0) { angle -= 360.0; }
      
      current_section_index = floor(angle / slice_angle);
  }

  if (current_section_index != last_pressed_joy_key_index) {
    // Release the previously held keys
    if (last_pressed_joy_key_index != -1) { 
      if(joy_keybinds[last_pressed_joy_key_index][0] != ' ') Keyboard.release(joy_keybinds[last_pressed_joy_key_index][0]);
      if(joy_keybinds[last_pressed_joy_key_index][1] != ' ') Keyboard.release(joy_keybinds[last_pressed_joy_key_index][1]);
    }
    // Press the new keys (if any)
    if (current_section_index != -1) { 
      if(joy_keybinds[current_section_index][0] != ' ') Keyboard.press(joy_keybinds[current_section_index][0]);
      if(joy_keybinds[current_section_index][1] != ' ') Keyboard.press(joy_keybinds[current_section_index][1]);
    }
    last_pressed_joy_key_index = current_section_index;
  }
}

void updateMouseJoystick() {
  int joyX = analogRead(JOY_X_PIN) - joyXCenter;
  int joyY = analogRead(JOY_Y_PIN) - joyYCenter;
  Serial.print("JOY:"); Serial.print(joyX); Serial.print(","); Serial.println(joyY);
  
  float xPercent = (float)joyX / 512.0 * 100.0;
  float yPercent = (float)joyY / 512.0 * 100.0;
  int moveX = 0, moveY = 0;

  if (abs(xPercent) > joystickDeadzone) {
    moveX = map(xPercent, (xPercent > 0 ? joystickDeadzone : -100), (xPercent > 0 ? 100 : -joystickDeadzone), (xPercent > 0 ? 1 : -cursorSpeed), (xPercent > 0 ? cursorSpeed : -1));
  }
  if (abs(yPercent) > joystickDeadzone) {
    moveY = -map(yPercent, (yPercent > 0 ? joystickDeadzone : -100), (yPercent > 0 ? 100 : -joystickDeadzone), (yPercent > 0 ? 1 : -cursorSpeed), (yPercent > 0 ? cursorSpeed : -1));
  }
  
  if (moveX != 0 || moveY != 0) {
    Mouse.move(moveX, moveY, 0);
  }
}

// =================================================================
// SERIAL COMMANDS & STATE MANAGEMENT
// =================================================================
void releaseAllInputs() {
  Mouse.release(MOUSE_LEFT); Mouse.release(MOUSE_RIGHT); Keyboard.releaseAll();
  isLeftPressed_mouse = false; isRightPressed_mouse = false;
  isHardSipKeyHeld_kbd = false; isSoftSipKeyHeld_kbd = false; isSoftPuffKeyHeld_kbd = false; isHardPuffKeyHeld_kbd = false;
  
  if (last_pressed_joy_key_index != -1) {
    if(joy_keybinds[last_pressed_joy_key_index][0] != ' ') Keyboard.release(joy_keybinds[last_pressed_joy_key_index][0]);
    if(joy_keybinds[last_pressed_joy_key_index][1] != ' ') Keyboard.release(joy_keybinds[last_pressed_joy_key_index][1]);
    last_pressed_joy_key_index = -1;
  }
}

void handleSerialCommands() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n'); command.trim();
    
    if (command.equalsIgnoreCase("SET_MODE_MOUSE")) { releaseAllInputs(); currentMode = MODE_MOUSE; Serial.println("ACK:Mode set to MOUSE"); return; }
    if (command.equalsIgnoreCase("SET_MODE_KEYBOARD")) { releaseAllInputs(); currentMode = MODE_KEYBOARD; Serial.println("ACK:Mode set to KEYBOARD"); return; }
    if (command.equalsIgnoreCase("START_CALIBRATION")) { releaseAllInputs(); calibrationModeActive = true; Serial.println("ACK:Calibration started"); return; }
    if (command.equalsIgnoreCase("STOP_CALIBRATION")) { calibrationModeActive = false; Serial.println("ACK:Calibration stopped"); return; }

    int colonIndex = command.indexOf(':'); if (colonIndex == -1) return;
    String cmd_key = command.substring(0, colonIndex);
    String cmd_val_str = command.substring(colonIndex + 1);
    
    // *** NEW: Command format for key combos is SET_JOY_KEY:index,key1_ascii,key2_ascii ***
    if (cmd_key.equalsIgnoreCase("SET_JOY_KEY")) {
      int first_comma = cmd_val_str.indexOf(',');
      int second_comma = cmd_val_str.indexOf(',', first_comma + 1);
      
      if (first_comma != -1 && second_comma != -1) {
        int index = cmd_val_str.substring(0, first_comma).toInt();
        int ascii_val1 = cmd_val_str.substring(first_comma + 1, second_comma).toInt();
        int ascii_val2 = cmd_val_str.substring(second_comma + 1).toInt();
        
        if (index >= 0 && index < 16) {
          joy_keybinds[index][0] = (byte)ascii_val1;
          joy_keybinds[index][1] = (byte)ascii_val2;
        }
      }
    } else { // Handle all other commands
        int val = cmd_val_str.toInt();
        if (cmd_key.equalsIgnoreCase("SET_HST")) { hardSipThreshold = val; }
        else if (cmd_key.equalsIgnoreCase("SET_NMIN")) { neutralMin = val; }
        else if (cmd_key.equalsIgnoreCase("SET_NMAX")) { neutralMax = val; }
        else if (cmd_key.equalsIgnoreCase("SET_SPT")) { softPuffThreshold = val; }
        else if (cmd_key.equalsIgnoreCase("SET_HPT")) { hardPuffThreshold = val; }
        else if (cmd_key.equalsIgnoreCase("SET_JDZ")) { joystickDeadzone = val; }
        else if (cmd_key.equalsIgnoreCase("SET_JMT")) { joystickMovementThreshold = val; }
        else if (cmd_key.equalsIgnoreCase("SET_CSP")) { cursorSpeed = val; }
        else if (cmd_key.equalsIgnoreCase("SET_SAD")) { softActionDelay = val; }
        else if (cmd_key.equalsIgnoreCase("SET_SIP_SENS")) { sipSensitivity = val; }
        else if (cmd_key.equalsIgnoreCase("SET_PUFF_SENS")) { puffSensitivity = val; }
        else if (cmd_key.equalsIgnoreCase("SET_KEY_HPT")) { key_hpt = val; }
        else if (cmd_key.equalsIgnoreCase("SET_KEY_SPT")) { key_spt = val; }
        else if (cmd_key.equalsIgnoreCase("SET_KEY_HST")) { key_hst = val; }
        else if (cmd_key.equalsIgnoreCase("SET_KEY_SST")) { key_sst = val; }
        else if (cmd_key.equalsIgnoreCase("SET_NUM_SECTORS")) { num_joy_sections = val; }
    }
  }
}