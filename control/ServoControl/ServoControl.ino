/*
  ServoControl.ino
  Controls 12 servos connected to a PCA9685 16-channel servo controller
  via commands received over Serial from a Python GUI.
  
  Connections:
  - Arduino Nano A4 (SDA) -> PCA9685 SDA
  - Arduino Nano A5 (SCL) -> PCA9685 SCL
  - Arduino Nano GND      -> PCA9685 GND
  - Arduino Nano 5V       -> PCA9685 VCC (logic power)
  - External Power (5V/6V) -> PCA9685 V+ and GND screw terminals (servo power)
  
  Serial Command Format:
  "servo_channel:angle_degrees\n"
  Example: "3:90\n" sets servo channel 3 to 90 degrees.
  
  Allowed servo channels: 0 to 11
  Allowed angle range: 45 to 135 degrees (centered around 90, representing -45 to 45 deg)
*/

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// Initialize the PCA9685 driver (default I2C address is 0x40)
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

#define SERVO_FREQ 50 // Standard analog servo update rate (50 Hz)

// Pulse width limits (in microseconds) corresponding to 0 and 180 degrees.
// Typical analog hobby servos (like SG90) use 1000us (0 deg) to 2000us (180 deg),
// or a wider range of 600us (0 deg) to 2400us (180 deg) for full 180 degrees.
// Here we use 600us to 2400us as a standard default. You can fine-tune these if needed.
#define USMIN  600  // Microsecond pulse width for 0 degrees
#define USMAX  2400 // Microsecond pulse width for 180 degrees

// Number of servos we are controlling (0 to 11 on the PCA9685 channels 0 to 11)
const int NUM_SERVOS = 12;

void setup() {
  // Initialize serial communication at 115200 baud rate
  Serial.begin(115200);
  while (!Serial) {
    ; // Wait for serial port to connect (needed for Leonardo/Micro boards, good practice)
  }
  
  Serial.println("INIT: Arduino Nano PCA9685 Servo Control Ready");

  // Initialize the PCA9685 board
  pwm.begin();
  pwm.setOscillatorFrequency(27000000); // Set oscillator frequency
  pwm.setPWMFreq(SERVO_FREQ);           // Set PWM frequency to 50Hz

  // Initialize all 12 servos to their center position (90 degrees, absolute)
  for (int i = 0; i < NUM_SERVOS; i++) {
    setServoAngle(i, 90);
  }
}

void loop() {
  // Check if serial data is available
  if (Serial.available() > 0) {
    // Read command string until newline character
    String command = Serial.readStringUntil('\n');
    command.trim(); // Remove leading/trailing whitespaces
    

    if (command.length() > 0) {
      // Find the separator character ':'
      int colonIdx = command.indexOf(':');
      if (colonIdx != -1) {
        // Extract channel and angle substrings
        String channelStr = command.substring(0, colonIdx);
        String angleStr = command.substring(colonIdx + 1);

        int channel = channelStr.toInt();
        int angle = angleStr.toInt();

        // Validate that the channel is between 0 and 11
        if (channel >= 0 && channel < NUM_SERVOS) {
          // Validate angle range (0 to 180 degrees)
          if (angle >= 0 && angle <= 180) {
            setServoAngle(channel, angle);
          } else {
            Serial.println("ERR: Angle out of bounds (0-180)");
          }
        } else {
          Serial.println("ERR: Invalid channel (must be 0-11)");
        }
      } else {
        Serial.println("ERR: Invalid format (use channel:angle)");
      }
    }
  }
}

// Maps angle (0-180) to microseconds (USMIN-USMAX) and sets PWM output
void setServoAngle(int channel, int angle) {
  uint16_t pulseWidth = map(angle, 0, 180, USMIN, USMAX);
  pwm.writeMicroseconds(channel, pulseWidth);
}
