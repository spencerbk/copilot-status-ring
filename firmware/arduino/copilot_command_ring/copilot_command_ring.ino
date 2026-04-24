// SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
// SPDX-License-Identifier: MIT
//
// Copilot Command Ring — Arduino firmware
//
// State-machine-driven NeoPixel ring controller.  Receives JSON Lines over
// USB serial from the host bridge and drives animations accordingly.
//
// Compile with USE_ARDUINOJSON defined to use ArduinoJson v7 for parsing,
// otherwise a lightweight strstr-based extractor is used.

#include <Adafruit_NeoPixel.h>

#ifdef USE_ARDUINOJSON
#include <ArduinoJson.h>
#endif

// ---------------------------------------------------------------------------
// USB identification
// Sets the USB product name so the host bridge can auto-detect the device.
// Platform-specific — uncomment the section that matches your board.
// ---------------------------------------------------------------------------

// Adafruit boards with TinyUSB (SAMD, nRF, RP2040 Adafruit core):
// #include "Adafruit_TinyUSB.h"
// — then in setup(): TinyUSBDevice.setProductDescriptor("Copilot Command Ring");

// RP2040 (Earle Philhower core):
// Add to Arduino IDE build flags: -DUSB_PRODUCT="Copilot Command Ring"
// Or set via Tools > USB Stack > Adafruit TinyUSB and use the TinyUSB approach above.

// ESP32-S2/S3:
// #include "USB.h"
// — then in setup(): USB.productName("Copilot Command Ring");

// ---------------------------------------------------------------------------
// Configuration
// Data pin — change to match your board:
//   Arduino Uno/Nano, Pico, XIAO ESP32-C6: 6 (default)
//   QT Py ESP32-S2/S3:                     A0
// ---------------------------------------------------------------------------

#define NEOPIXEL_PIN    6
#define PIXEL_COUNT     24
#define BRIGHTNESS      10    // 0-255, ~4%
#define SERIAL_BAUD     115200
#define SERIAL_BUF_SIZE 256

// ---------------------------------------------------------------------------
// State enum
// ---------------------------------------------------------------------------

enum State {
  ST_OFF,
  ST_SESSION_START,
  ST_PROMPT_SUBMITTED,
  ST_WORKING,
  ST_TOOL_OK,
  ST_TOOL_ERROR,
  ST_TOOL_DENIED,
  ST_AWAITING_PERMISSION,
  ST_AWAITING_ELICITATION,
  ST_SUBAGENT_ACTIVE,
  ST_AGENT_IDLE,
  ST_COMPACTING,
  ST_ERROR,
  ST_NOTIFY,
  ST_IDLE
};

// ---------------------------------------------------------------------------
// Color palette  (GRB order handled by library — pass as RGB)
// ---------------------------------------------------------------------------

static const uint32_t COL_SESSION_START = Adafruit_NeoPixel::Color(60, 60, 50);
static const uint32_t COL_PROMPT       = Adafruit_NeoPixel::Color(0, 152, 255);    // #0098FF
static const uint32_t COL_WORKING      = Adafruit_NeoPixel::Color(150, 56, 133);   // magenta (#963885)
static const uint32_t COL_TOOL_OK      = Adafruit_NeoPixel::Color(15, 191, 62);    // #0FBF3E
static const uint32_t COL_TOOL_ERROR   = Adafruit_NeoPixel::Color(218, 54, 51);    // #DA3633
static const uint32_t COL_TOOL_DENIED  = Adafruit_NeoPixel::Color(210, 153, 34);   // #D29922 — user denied a tool
static const uint32_t COL_PERMISSION   = Adafruit_NeoPixel::Color(210, 153, 34);   // #D29922
static const uint32_t COL_ELICITATION  = Adafruit_NeoPixel::Color(210, 153, 34);   // #D29922 — same hue, distinct anim
static const uint32_t COL_SUBAGENT     = Adafruit_NeoPixel::Color(150, 56, 133);   // magenta (#963885)
static const uint32_t COL_AGENT_IDLE   = Adafruit_NeoPixel::Color(40, 40, 35);
static const uint32_t COL_COMPACTING   = Adafruit_NeoPixel::Color(0, 180, 180);
static const uint32_t COL_ERROR        = Adafruit_NeoPixel::Color(218, 54, 51);    // #DA3633
static const uint32_t COL_NOTIFY       = Adafruit_NeoPixel::Color(200, 200, 200);

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------

Adafruit_NeoPixel ring(PIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);

static State currentState  = ST_OFF;
static State prevState     = ST_OFF;
static State savedState    = ST_OFF;
static unsigned long stateStartMs = 0;
static int animStep        = 0;
static unsigned long savedStartMs = 0;
static int savedStep       = 0;

static char serialBuf[SERIAL_BUF_SIZE];
static uint8_t serialIdx   = 0;

// ---------------------------------------------------------------------------
// Helper: sine-based brightness (0.0–1.0)
// ---------------------------------------------------------------------------

static float sineBrightness(unsigned long elapsed, unsigned long period) {
  float phase = (float)(elapsed % period) / (float)period;
  // sin gives -1..1, remap to 0..1
  float val = (sin(phase * 2.0f * PI) + 1.0f) * 0.5f;
  return val;
}

// ---------------------------------------------------------------------------
// Helper: scale a packed color by a 0.0–1.0 factor
// ---------------------------------------------------------------------------

static uint32_t scaleColor(uint32_t color, float factor) {
  uint8_t r = (uint8_t)(((color >> 16) & 0xFF) * factor);
  uint8_t g = (uint8_t)(((color >> 8)  & 0xFF) * factor);
  uint8_t b = (uint8_t)((color & 0xFF) * factor);
  return Adafruit_NeoPixel::Color(r, g, b);
}

// ---------------------------------------------------------------------------
// Transient state check
// ---------------------------------------------------------------------------

static bool isTransient(State s) {
  return (s == ST_TOOL_OK || s == ST_TOOL_ERROR || s == ST_TOOL_DENIED || s == ST_ERROR || s == ST_NOTIFY);
}

// ---------------------------------------------------------------------------
// State parsing
// ---------------------------------------------------------------------------

static void setState(State s) {
  if (s == currentState) return;

  // Returning from a transient flash to the same persistent state —
  // restore saved animation timing so the spinner continues seamlessly.
  if (isTransient(currentState) && s == savedState) {
    prevState    = s;
    currentState = s;
    stateStartMs = savedStartMs;
    animStep     = savedStep;
    return;
  }

  // Entering a transient — save current timing only from a non-transient
  // state so nested transients don't overwrite the original timing.
  if (isTransient(s) && !isTransient(currentState)) {
    savedState   = currentState;
    savedStartMs = stateStartMs;
    savedStep    = animStep;
  }

  prevState    = currentState;
  currentState = s;
  stateStartMs = millis();
  animStep     = 0;
}

static State stateFromStr(const char* s) {
  if (!s) return ST_OFF;
  if (strcmp(s, "off") == 0)                 return ST_OFF;
  if (strcmp(s, "session_start") == 0)       return ST_SESSION_START;
  if (strcmp(s, "prompt_submitted") == 0)    return ST_PROMPT_SUBMITTED;
  if (strcmp(s, "working") == 0)             return ST_WORKING;
  if (strcmp(s, "tool_ok") == 0)             return ST_TOOL_OK;
  if (strcmp(s, "tool_error") == 0)          return ST_TOOL_ERROR;
  if (strcmp(s, "tool_denied") == 0)         return ST_TOOL_DENIED;
  if (strcmp(s, "awaiting_permission") == 0) return ST_AWAITING_PERMISSION;
  if (strcmp(s, "awaiting_elicitation") == 0) return ST_AWAITING_ELICITATION;
  if (strcmp(s, "subagent_active") == 0)     return ST_SUBAGENT_ACTIVE;
  if (strcmp(s, "agent_idle") == 0)          return ST_AGENT_IDLE;
  if (strcmp(s, "compacting") == 0)          return ST_COMPACTING;
  if (strcmp(s, "error") == 0)               return ST_ERROR;
  if (strcmp(s, "notify") == 0)              return ST_NOTIFY;
  if (strcmp(s, "idle") == 0)                return ST_IDLE;
  return ST_OFF;  // unknown → off
}

// ---------------------------------------------------------------------------
// JSON parsing — ArduinoJson path
// ---------------------------------------------------------------------------

#ifdef USE_ARDUINOJSON

static void parseLine(const char* line) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) return;  // malformed → discard
  const char* st = doc["state"];
  if (st) setState(stateFromStr(st));
}

#else

// ---------------------------------------------------------------------------
// JSON parsing — lightweight fallback (strstr-based)
// ---------------------------------------------------------------------------

static void parseLine(const char* line) {
  // Look for "state" key and extract its value.
  const char* key = strstr(line, "\"state\"");
  if (!key) return;

  // Advance past the key and find the colon
  const char* p = key + 7;  // strlen("\"state\"")
  while (*p == ' ' || *p == '\t') p++;
  if (*p != ':') return;
  p++;
  while (*p == ' ' || *p == '\t') p++;

  // Expect opening quote of value
  if (*p != '"') return;
  p++;

  // Find closing quote
  const char* end = strchr(p, '"');
  if (!end || (end - p) >= 40) return;  // sanity limit

  // Copy value to a temp buffer
  char val[40];
  size_t len = (size_t)(end - p);
  memcpy(val, p, len);
  val[len] = '\0';

  setState(stateFromStr(val));
}

#endif  // USE_ARDUINOJSON

// ---------------------------------------------------------------------------
// Serial reading — accumulate chars, parse on newline
// ---------------------------------------------------------------------------

static void readSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialIdx > 0) {
        serialBuf[serialIdx] = '\0';
        // Trim leading whitespace
        char* trimmed = serialBuf;
        while (*trimmed == ' ' || *trimmed == '\t') trimmed++;
        // Trim trailing whitespace
        int tLen = (int)strlen(trimmed);
        while (tLen > 0 && (trimmed[tLen - 1] == ' ' || trimmed[tLen - 1] == '\t')) {
          trimmed[--tLen] = '\0';
        }
        if (tLen > 0) parseLine(trimmed);
        serialIdx = 0;
      }
    } else {
      if (serialIdx < SERIAL_BUF_SIZE - 1) {
        serialBuf[serialIdx++] = c;
      } else {
        // Buffer overflow — discard line
        serialIdx = 0;
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Animation: off
// ---------------------------------------------------------------------------

static void animOff() {
  ring.clear();
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: wipe — fill LEDs sequentially over `duration` ms
// ---------------------------------------------------------------------------

static void animWipe(uint32_t color, unsigned long duration) {
  unsigned long elapsed = millis() - stateStartMs;
  int lit = (int)((elapsed * PIXEL_COUNT) / duration);
  if (lit > PIXEL_COUNT) lit = PIXEL_COUNT;

  for (int i = 0; i < PIXEL_COUNT; i++) {
    ring.setPixelColor(i, (i < lit) ? color : 0);
  }
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: spinner — rotating segment of `width` LEDs, period ms per rev
// ---------------------------------------------------------------------------

static void animSpinner(uint32_t color, int width, unsigned long period) {
  unsigned long elapsed = millis() - stateStartMs;
  int head = (int)((elapsed % period) * PIXEL_COUNT / period);

  ring.clear();
  for (int i = 0; i < width; i++) {
    int idx = (head - i + PIXEL_COUNT) % PIXEL_COUNT;
    // Tail fade: dimmer LEDs further from head
    float bright = 1.0f - ((float)i / (float)width) * 0.7f;
    ring.setPixelColor(idx, scaleColor(color, bright));
  }
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: flash — solid color for `duration` ms then off
// ---------------------------------------------------------------------------

static void animFlash(uint32_t color, unsigned long duration) {
  unsigned long elapsed = millis() - stateStartMs;
  if (elapsed < duration) {
    for (int i = 0; i < PIXEL_COUNT; i++) ring.setPixelColor(i, color);
  } else {
    ring.clear();
  }
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: blink — on/off cycle with given period
// ---------------------------------------------------------------------------

static void animBlink(uint32_t color, unsigned long period) {
  unsigned long elapsed = millis() - stateStartMs;
  bool on = ((elapsed % period) < (period / 2));
  for (int i = 0; i < PIXEL_COUNT; i++) {
    ring.setPixelColor(i, on ? color : 0);
  }
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: chase — theater-chase pattern
// ---------------------------------------------------------------------------

static void animChase(uint32_t color, int spacing, unsigned long period) {
  unsigned long elapsed = millis() - stateStartMs;
  int offset = (int)((elapsed % period) * spacing / period);

  ring.clear();
  for (int i = 0; i < PIXEL_COUNT; i++) {
    if ((i + offset) % spacing == 0) {
      ring.setPixelColor(i, color);
    }
  }
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: breathing — sine-wave brightness modulation
// ---------------------------------------------------------------------------

static void animBreathing(uint32_t color, unsigned long period) {
  unsigned long elapsed = millis() - stateStartMs;
  float bright = sineBrightness(elapsed, period);
  // Clamp minimum so LEDs don't fully extinguish
  bright = 0.05f + bright * 0.95f;
  uint32_t scaled = scaleColor(color, bright);

  for (int i = 0; i < PIXEL_COUNT; i++) ring.setPixelColor(i, scaled);
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: pulse — sine-wave with raised floor (never fully dark)
// Visually distinct from blink (hard on/off) and breathing (fades to near-0).
// ---------------------------------------------------------------------------

static void animPulse(uint32_t color, unsigned long period) {
  unsigned long elapsed = millis() - stateStartMs;
  float bright = sineBrightness(elapsed, period);
  bright = 0.15f + bright * 0.85f;
  uint32_t scaled = scaleColor(color, bright);

  for (int i = 0; i < PIXEL_COUNT; i++) ring.setPixelColor(i, scaled);
  ring.show();
}

// ---------------------------------------------------------------------------
// Main animation dispatcher
// ---------------------------------------------------------------------------

static void animate() {
  switch (currentState) {
    case ST_OFF:
    case ST_IDLE:
      animOff();
      break;

    case ST_SESSION_START:
      animWipe(COL_SESSION_START, 1000);
      break;

    case ST_PROMPT_SUBMITTED:
      animSpinner(COL_PROMPT, 6, 1200);
      break;

    case ST_WORKING:
      animSpinner(COL_WORKING, 6, 800);
      break;

    case ST_TOOL_OK:
      animFlash(COL_TOOL_OK, 400);
      break;

    case ST_TOOL_ERROR:
      animFlash(COL_TOOL_ERROR, 400);
      break;

    case ST_TOOL_DENIED:
      animFlash(COL_TOOL_DENIED, 400);
      break;

    case ST_AWAITING_PERMISSION:
      animBlink(COL_PERMISSION, 800);
      break;

    case ST_AWAITING_ELICITATION:
      animPulse(COL_ELICITATION, 1500);
      break;

    case ST_SUBAGENT_ACTIVE:
      animChase(COL_SUBAGENT, 3, 600);
      break;

    case ST_AGENT_IDLE:
      animBreathing(COL_AGENT_IDLE, 3000);
      break;

    case ST_COMPACTING:
      animWipe(COL_COMPACTING, 1200);
      break;

    case ST_ERROR:
      animFlash(COL_ERROR, 800);
      break;

    case ST_NOTIFY:
      animFlash(COL_NOTIFY, 500);
      break;
  }
}

// ---------------------------------------------------------------------------
// Arduino entry points
// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(SERIAL_BAUD);
  ring.begin();
  ring.setBrightness(BRIGHTNESS);
  ring.clear();
  ring.show();
}

void loop() {
  readSerial();
  animate();
  delay(20);  // ~50 fps
}
