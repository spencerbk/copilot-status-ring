// SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
// SPDX-License-Identifier: MIT
//
// Copilot Command Ring — Arduino firmware
//
// Full-featured NeoPixel ring controller with multi-session tracking,
// TTL decay, priority arbitration, and idle-mode support.  Feature
// parity with the CircuitPython and MicroPython firmware variants.
//
// Receives JSON Lines over USB serial from the host bridge and drives
// animations on a 24-pixel NeoPixel ring.
//
// Compile with USE_ARDUINOJSON defined to use ArduinoJson v7 for parsing,
// otherwise a lightweight strstr-based extractor is used.

#include "copilot_types.h"
#include <Adafruit_NeoPixel.h>

#ifdef USE_ARDUINOJSON
#include <ArduinoJson.h>
#endif

// ---------------------------------------------------------------------------
// Platform-specific watchdog and reset
// ---------------------------------------------------------------------------

#if defined(ARDUINO_ARCH_RP2040)
  #include <hardware/watchdog.h>
  #define HAS_WATCHDOG 1
  static inline void wdtInit(uint32_t ms) { watchdog_enable(ms, true); }
  static inline void wdtFeed()            { watchdog_update(); }
  static inline void softReset()          { watchdog_reboot(0, 0, 0); }
#elif defined(ARDUINO_ARCH_ESP32)
  // ESP32 watchdog API varies across Arduino core versions.
  // Software reset is always available.
  #define HAS_WATCHDOG 0
  static inline void wdtInit(uint32_t) {}
  static inline void wdtFeed()         {}
  static inline void softReset()       { ESP.restart(); }
#else
  #define HAS_WATCHDOG 0
  static inline void wdtInit(uint32_t) {}
  static inline void wdtFeed()         {}
  static inline void softReset()       { for (;;) {} }
#endif

// ---------------------------------------------------------------------------
// USB identification  (platform-specific — see README.md for details)
// ---------------------------------------------------------------------------

// RP2040 (Earle Philhower core):
//   Add to build flags: -DUSB_PRODUCT="Copilot Command Ring"
// ESP32-S2/S3:
//   #include "USB.h"
//   then in setup(): USB.productName("Copilot Command Ring");
// Adafruit TinyUSB boards:
//   #include "Adafruit_TinyUSB.h"
//   then in setup(): TinyUSBDevice.setProductDescriptor("Copilot Command Ring");

// ---------------------------------------------------------------------------
// Color palette  (GRB order handled by library — pass as RGB)
// ---------------------------------------------------------------------------

static const uint32_t COL_SESSION_START = Adafruit_NeoPixel::Color(60, 60, 50);
static const uint32_t COL_PROMPT        = Adafruit_NeoPixel::Color(0, 152, 255);
static const uint32_t COL_WORKING       = Adafruit_NeoPixel::Color(150, 56, 133);
static const uint32_t COL_TOOL_OK       = Adafruit_NeoPixel::Color(15, 191, 62);
static const uint32_t COL_TOOL_ERROR    = Adafruit_NeoPixel::Color(218, 54, 51);
static const uint32_t COL_TOOL_DENIED   = Adafruit_NeoPixel::Color(210, 153, 34);
static const uint32_t COL_PERMISSION    = Adafruit_NeoPixel::Color(210, 153, 34);
static const uint32_t COL_ELICITATION   = Adafruit_NeoPixel::Color(210, 153, 34);
static const uint32_t COL_SUBAGENT      = Adafruit_NeoPixel::Color(150, 56, 133);
static const uint32_t COL_AGENT_IDLE    = Adafruit_NeoPixel::Color(40, 40, 35);
static const uint32_t COL_COMPACTING    = Adafruit_NeoPixel::Color(0, 180, 180);
static const uint32_t COL_ERROR         = Adafruit_NeoPixel::Color(218, 54, 51);
static const uint32_t COL_NOTIFY        = Adafruit_NeoPixel::Color(200, 200, 200);

// ---------------------------------------------------------------------------
// State classification and priority
// ---------------------------------------------------------------------------

// Priority for multi-session arbitration.  Higher value wins.
// Matches CircuitPython STATE_PRIORITY exactly.
static const int8_t STATE_PRIORITY[ST_COUNT] = {
  /* ST_OFF */                  0,
  /* ST_SESSION_START */        3,
  /* ST_PROMPT_SUBMITTED */     4,
  /* ST_WORKING */              7,
  /* ST_TOOL_OK */              0,   // transient
  /* ST_TOOL_ERROR */           0,   // transient
  /* ST_TOOL_DENIED */          0,   // transient
  /* ST_AWAITING_PERMISSION */  8,
  /* ST_AWAITING_ELICITATION */ 9,
  /* ST_SUBAGENT_ACTIVE */      6,
  /* ST_AGENT_IDLE */           2,
  /* ST_COMPACTING */           5,
  /* ST_ERROR */                10,
  /* ST_NOTIFY */               0,   // transient
  /* ST_IDLE */                 1,
};

static bool isTransient(State s) {
  return s == ST_TOOL_OK || s == ST_TOOL_ERROR || s == ST_TOOL_DENIED
      || s == ST_ERROR   || s == ST_NOTIFY;
}

static bool isBoosted(State s) {
  return s == ST_AGENT_IDLE;
}

// Suppress white notification flashes while clearly busy.
static bool isNotifySuppressed(State s) {
  return s == ST_WORKING || s == ST_SUBAGENT_ACTIVE || s == ST_COMPACTING;
}

// Flash duration (ms) for transient states.
static unsigned long flashDurationMs(State s) {
  switch (s) {
    case ST_ERROR: return 800;
    default:       return 300;
  }
}

static bool shouldApplyTransient(State persistent, State transient) {
  // While the CLI is blocked on user input, only a hard error overrides.
  if (persistent == ST_AWAITING_ELICITATION)
    return transient == ST_ERROR;
  // Notify is suppressed while a clearly busy animation is visible.
  if (transient == ST_NOTIFY)
    return !isNotifySuppressed(persistent);
  return true;
}

// ---------------------------------------------------------------------------
// Session tracker
// ---------------------------------------------------------------------------

static SessionEntry sessions[MAX_SESSIONS];
static uint8_t      sessionCount        = 0;
static State        pendingTransient    = ST_OFF;
static bool         hasPendingTransient = false;
static IdleMode     globalIdleMode      = IDLE_BREATHING;
static bool         staleIdle           = true;  // breathe by default on boot

static void refreshFallback() {
  staleIdle = (globalIdleMode != IDLE_OFF);
}

static int8_t trackerFind(const char* sid) {
  for (uint8_t i = 0; i < MAX_SESSIONS; i++) {
    if (sessions[i].occupied && strcmp(sessions[i].id, sid) == 0)
      return (int8_t)i;
  }
  return -1;
}

static int8_t trackerAllocate() {
  for (uint8_t i = 0; i < MAX_SESSIONS; i++) {
    if (!sessions[i].occupied) return (int8_t)i;
  }
  return -1;
}

static void trackerRemove(int8_t idx) {
  if (idx >= 0 && idx < MAX_SESSIONS) {
    sessions[idx].occupied = false;
    sessionCount--;
  }
}

static void trackerUpdate(const ParsedMessage& msg, uint32_t now) {
  // Propagate idle_mode
  if (msg.idleMode != IDLE_UNSET) {
    globalIdleMode = msg.idleMode;
    if (sessionCount == 0) refreshFallback();
  }

  // Transient: set pending, touch session timestamp, don't modify persistent
  if (isTransient(msg.state)) {
    hasPendingTransient = true;
    pendingTransient = msg.state;
    if (msg.session[0] != '\0') {
      int8_t idx = trackerFind(msg.session);
      if (idx >= 0) sessions[idx].lastSeenMs = now;
    }
    return;
  }

  // "off" = session ended
  if (msg.state == ST_OFF) {
    if (msg.session[0] != '\0') {
      int8_t idx = trackerFind(msg.session);
      if (idx >= 0) trackerRemove(idx);
    }
    if (sessionCount == 0) refreshFallback();
    return;
  }

  // Persistent state — session-tagged only
  if (msg.session[0] == '\0') return;

  int8_t idx = trackerFind(msg.session);
  if (idx >= 0) {
    sessions[idx].persistent = msg.state;
    sessions[idx].lastSeenMs = now;
    sessions[idx].ttlMs      = msg.ttlMs;
    sessions[idx].hasTtl     = msg.hasTtl;
  } else {
    // Allocate or evict oldest
    idx = trackerAllocate();
    if (idx < 0) {
      int8_t oldest = -1;
      uint32_t oldestAge = 0;
      for (uint8_t i = 0; i < MAX_SESSIONS; i++) {
        if (sessions[i].occupied) {
          uint32_t age = now - sessions[i].lastSeenMs;
          if (oldest < 0 || age > oldestAge) {
            oldest = (int8_t)i;
            oldestAge = age;
          }
        }
      }
      if (oldest >= 0) trackerRemove(oldest);
      idx = trackerAllocate();
    }
    if (idx >= 0) {
      strncpy(sessions[idx].id, msg.session, SESSION_ID_LEN - 1);
      sessions[idx].id[SESSION_ID_LEN - 1] = '\0';
      sessions[idx].persistent = msg.state;
      sessions[idx].lastSeenMs = now;
      sessions[idx].ttlMs      = msg.ttlMs;
      sessions[idx].hasTtl     = msg.hasTtl;
      sessions[idx].occupied   = true;
      sessionCount++;
    }
  }
}

static ResolveResult trackerResolve(uint32_t now) {
  // Prune stale sessions
  bool pruned = false;
  for (uint8_t i = 0; i < MAX_SESSIONS; i++) {
    if (sessions[i].occupied && (now - sessions[i].lastSeenMs) > STALE_TIMEOUT_MS) {
      sessions[i].occupied = false;
      sessionCount--;
      pruned = true;
    }
  }

  ResolveResult r;
  r.transient    = pendingTransient;
  r.hasTransient = hasPendingTransient;
  hasPendingTransient = false;
  pendingTransient    = ST_OFF;

  if (sessionCount == 0) {
    if (pruned) refreshFallback();
    r.winning = staleIdle ? ST_AGENT_IDLE : ST_OFF;
    return r;
  }

  // Find highest-priority active session
  State bestState   = ST_OFF;
  int8_t bestPri    = -1;
  uint32_t bestTime = 0;
  for (uint8_t i = 0; i < MAX_SESSIONS; i++) {
    if (!sessions[i].occupied) continue;
    State effective = sessions[i].persistent;
    // TTL decay: treat expired sessions as agent_idle
    if (sessions[i].hasTtl && (now - sessions[i].lastSeenMs) > sessions[i].ttlMs) {
      effective = ST_AGENT_IDLE;
    }
    int8_t pri = STATE_PRIORITY[effective];
    // Higher priority wins.  Equal priority: most recent lastSeen wins.
    if (pri > bestPri || (pri == bestPri && sessions[i].lastSeenMs > bestTime)) {
      bestPri   = pri;
      bestState = effective;
      bestTime  = sessions[i].lastSeenMs;
    }
  }

  r.winning = bestState;
  return r;
}

// ---------------------------------------------------------------------------
// Ring + animation globals
// ---------------------------------------------------------------------------

Adafruit_NeoPixel ring(PIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);

static State         currentState    = ST_OFF;
static State         prevState       = ST_OFF;
static State         savedState      = ST_OFF;
static unsigned long stateStartMs    = 0;
static int           animStep        = 0;
static unsigned long savedStartMs    = 0;
static int           savedStep       = 0;
static uint16_t      runtimePixelCount = PIXEL_COUNT;
static uint8_t       runtimeBrightness = BRIGHTNESS;

// Serial state
static char    serialBuf[SERIAL_BUF_SIZE];
static uint8_t serialIdx = 0;

// Per-loop flags set by readSerial()
static bool  rsHasSession = false;
static bool  rsParsedAny  = false;
static State rsLatestBare = ST_OFF;
static bool  rsHasBare    = false;

// Legacy bare-state tracking (for messages without a session field)
static State legacyBareState = ST_OFF;
static bool  legacyBareValid = false;

// Error and silence tracking
static uint32_t lastRxMs          = 0;
static uint8_t  consecutiveErrors = 0;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static float sineBrightness(unsigned long elapsed, unsigned long period) {
  float phase = (float)(elapsed % period) / (float)period;
  // Match CircuitPython: sin(2*pi*phase - pi/2) starts at 0 brightness
  return (sin(phase * 2.0f * PI - PI / 2.0f) + 1.0f) * 0.5f;
}

static uint32_t scaleColor(uint32_t color, float factor) {
  uint8_t r = (uint8_t)(((color >> 16) & 0xFF) * factor);
  uint8_t g = (uint8_t)(((color >> 8)  & 0xFF) * factor);
  uint8_t b = (uint8_t)((color & 0xFF) * factor);
  return Adafruit_NeoPixel::Color(r, g, b);
}

static uint8_t stateBrightness(State s) {
  uint16_t value = runtimeBrightness;
  if (isBoosted(s)) value += BRIGHTNESS_BOOST;
  return value > 255 ? 255 : (uint8_t)value;
}

// ---------------------------------------------------------------------------
// State management
// ---------------------------------------------------------------------------

static void setState(State s) {
  if (s == currentState) return;

  // Flash-duration guard: don't revert from transient to saved state
  // until the flash animation has finished playing.
  if (isTransient(currentState) && s == savedState) {
    unsigned long elapsed = millis() - stateStartMs;
    if (elapsed < flashDurationMs(currentState))
      return;
    prevState    = s;
    currentState = s;
    stateStartMs = savedStartMs;
    animStep     = savedStep;
    if (isBoosted(s))
      ring.setBrightness(stateBrightness(s));
    return;
  }

  // Entering a transient — save current timing from non-transient only
  if (isTransient(s) && !isTransient(currentState)) {
    savedState   = currentState;
    savedStartMs = stateStartMs;
    savedStep    = animStep;
  }

  prevState    = currentState;
  currentState = s;
  stateStartMs = millis();
  animStep     = 0;

  // Brightness boost for dim states (only on transitions)
  if (isBoosted(s) || isBoosted(prevState))
    ring.setBrightness(stateBrightness(s));
}

static State stateFromStr(const char* s) {
  if (!s) return ST_OFF;
  if (strcmp(s, "off") == 0)                  return ST_OFF;
  if (strcmp(s, "session_start") == 0)        return ST_SESSION_START;
  if (strcmp(s, "prompt_submitted") == 0)     return ST_PROMPT_SUBMITTED;
  if (strcmp(s, "working") == 0)              return ST_WORKING;
  if (strcmp(s, "tool_ok") == 0)              return ST_TOOL_OK;
  if (strcmp(s, "tool_error") == 0)           return ST_TOOL_ERROR;
  if (strcmp(s, "tool_denied") == 0)          return ST_TOOL_DENIED;
  if (strcmp(s, "awaiting_permission") == 0)  return ST_AWAITING_PERMISSION;
  if (strcmp(s, "awaiting_elicitation") == 0) return ST_AWAITING_ELICITATION;
  if (strcmp(s, "subagent_active") == 0)      return ST_SUBAGENT_ACTIVE;
  if (strcmp(s, "agent_idle") == 0)           return ST_AGENT_IDLE;
  if (strcmp(s, "compacting") == 0)           return ST_COMPACTING;
  if (strcmp(s, "error") == 0)                return ST_ERROR;
  if (strcmp(s, "notify") == 0)               return ST_NOTIFY;
  if (strcmp(s, "idle") == 0)                 return ST_IDLE;
  return ST_OFF;  // unknown -> off
}

// ---------------------------------------------------------------------------
// JSON parsing — ArduinoJson path
// ---------------------------------------------------------------------------

#ifdef USE_ARDUINOJSON

static ParsedMessage parseLine(const char* line) {
  ParsedMessage msg = {};
  msg.state      = ST_OFF;
  msg.session[0] = '\0';
  msg.hasTtl     = false;
  msg.idleMode   = IDLE_UNSET;
  msg.hasBrightness = false;
  msg.hasPixelCount = false;
  msg.valid      = false;

  JsonDocument doc;
  if (deserializeJson(doc, line)) return msg;

  const char* st = doc["state"];
  if (st) msg.state = stateFromStr(st);

  const char* sid = doc["session"];
  if (sid) {
    strncpy(msg.session, sid, SESSION_ID_LEN - 1);
    msg.session[SESSION_ID_LEN - 1] = '\0';
  }

  if (doc["ttl_s"].is<float>()) {
    float ttl = doc["ttl_s"];
    if (ttl > 0) {
      msg.ttlMs  = (uint32_t)(ttl * 1000.0f);
      msg.hasTtl = true;
    }
  }

  if (doc["brightness"].is<float>()) {
    float brightness = doc["brightness"];
    if (brightness >= 0.0f && brightness <= 1.0f) {
      msg.brightness = (uint8_t)(brightness * 255.0f + 0.5f);
      msg.hasBrightness = true;
    }
  }

  if (doc["pixel_count"].is<int>()) {
    int pixelCount = doc["pixel_count"];
    if (pixelCount > 0 && pixelCount <= MAX_RUNTIME_PIXELS) {
      msg.pixelCount = (uint16_t)pixelCount;
      msg.hasPixelCount = true;
    }
  }

  const char* im = doc["idle_mode"];
  if (im) {
    if (strcmp(im, "breathing") == 0) msg.idleMode = IDLE_BREATHING;
    else if (strcmp(im, "off") == 0)  msg.idleMode = IDLE_OFF;
  }

  msg.valid = true;
  return msg;
}

#else

// ---------------------------------------------------------------------------
// JSON parsing — lightweight strstr-based extraction
// ---------------------------------------------------------------------------

static size_t extractStr(const char* line, const char* key, size_t keyLen,
                         char* buf, size_t bufSize) {
  const char* k = strstr(line, key);
  if (!k) return 0;
  const char* p = k + keyLen;
  while (*p == ' ' || *p == '\t') p++;
  if (*p != ':') return 0;
  p++;
  while (*p == ' ' || *p == '\t') p++;
  if (*p != '"') return 0;
  p++;
  const char* end = strchr(p, '"');
  if (!end || (size_t)(end - p) >= bufSize) return 0;
  size_t len = (size_t)(end - p);
  memcpy(buf, p, len);
  buf[len] = '\0';
  return len;
}

static bool extractNum(const char* line, const char* key, size_t keyLen,
                        float* out) {
  const char* k = strstr(line, key);
  if (!k) return false;
  const char* p = k + keyLen;
  while (*p == ' ' || *p == '\t') p++;
  if (*p != ':') return false;
  p++;
  while (*p == ' ' || *p == '\t') p++;
  char* endp;
  double val = strtod(p, &endp);
  if (endp == p) return false;
  *out = (float)val;
  return true;
}

static ParsedMessage parseLine(const char* line) {
  ParsedMessage msg = {};
  msg.state      = ST_OFF;
  msg.session[0] = '\0';
  msg.hasTtl     = false;
  msg.idleMode   = IDLE_UNSET;
  msg.hasBrightness = false;
  msg.hasPixelCount = false;
  msg.valid      = false;

  char val[40];
  if (extractStr(line, "\"state\"", 7, val, sizeof(val))) {
    msg.state = stateFromStr(val);
  } else {
    return msg;  // no state key = invalid
  }

  extractStr(line, "\"session\"", 9, msg.session, SESSION_ID_LEN);

  float ttl;
  if (extractNum(line, "\"ttl_s\"", 7, &ttl) && ttl > 0) {
    msg.ttlMs  = (uint32_t)(ttl * 1000.0f);
    msg.hasTtl = true;
  }

  float brightness;
  if (extractNum(line, "\"brightness\"", 12, &brightness)
      && brightness >= 0.0f && brightness <= 1.0f) {
    msg.brightness = (uint8_t)(brightness * 255.0f + 0.5f);
    msg.hasBrightness = true;
  }

  float pixelCount;
  if (extractNum(line, "\"pixel_count\"", 13, &pixelCount)
      && pixelCount >= 1.0f && pixelCount <= (float)MAX_RUNTIME_PIXELS) {
    uint16_t pixelCountInt = (uint16_t)pixelCount;
    if (pixelCount == (float)pixelCountInt) {
      msg.pixelCount = pixelCountInt;
      msg.hasPixelCount = true;
    }
  }

  char im[16];
  if (extractStr(line, "\"idle_mode\"", 11, im, sizeof(im))) {
    if (strcmp(im, "breathing") == 0) msg.idleMode = IDLE_BREATHING;
    else if (strcmp(im, "off") == 0)  msg.idleMode = IDLE_OFF;
  }

  msg.valid = true;
  return msg;
}

#endif  // USE_ARDUINOJSON

// ---------------------------------------------------------------------------
// Serial reading
// ---------------------------------------------------------------------------

static void applyRuntimeConfig(const ParsedMessage& msg) {
  if (msg.hasBrightness) {
    runtimeBrightness = msg.brightness;
    ring.setBrightness(stateBrightness(currentState));
  }

  if (msg.hasPixelCount && msg.pixelCount != runtimePixelCount) {
    ring.clear();
    ring.show();
    ring.updateLength(msg.pixelCount);
    runtimePixelCount = msg.pixelCount;
    ring.setBrightness(stateBrightness(currentState));
    animStep = 0;
  }
}

static void processMessage(const ParsedMessage& msg, uint32_t now) {
  applyRuntimeConfig(msg);

  if (msg.session[0] != '\0') {
    rsHasSession = true;
    trackerUpdate(msg, now);
  } else {
    rsLatestBare = msg.state;
    rsHasBare    = true;
    // Bare idle_mode propagates to global preference
    if (msg.idleMode != IDLE_UNSET) {
      globalIdleMode = msg.idleMode;
      if (sessionCount == 0) refreshFallback();
    }
    // Bare transient: push into tracker pending so overlay logic can use it
    if (isTransient(msg.state)) {
      hasPendingTransient = true;
      pendingTransient = msg.state;
    }
  }
}

static void readSerial() {
  rsHasSession = false;
  rsParsedAny  = false;
  rsLatestBare = ST_OFF;
  rsHasBare    = false;

  uint32_t now = millis();
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialIdx > 0) {
        serialBuf[serialIdx] = '\0';
        char* trimmed = serialBuf;
        while (*trimmed == ' ' || *trimmed == '\t') trimmed++;
        int tLen = (int)strlen(trimmed);
        while (tLen > 0 && (trimmed[tLen - 1] == ' ' || trimmed[tLen - 1] == '\t'))
          trimmed[--tLen] = '\0';
        if (tLen > 0) {
          ParsedMessage msg = parseLine(trimmed);
          if (msg.valid) {
            processMessage(msg, now);
            rsParsedAny = true;
            consecutiveErrors = 0;
          } else {
            consecutiveErrors++;
          }
        }
        serialIdx = 0;
      }
    } else {
      if (serialIdx < SERIAL_BUF_SIZE - 1) {
        serialBuf[serialIdx++] = c;
      } else {
        serialIdx = 0;  // overflow — discard line
        consecutiveErrors++;
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
// Animation: wipe — fill LEDs sequentially over duration ms
// ---------------------------------------------------------------------------

static void animWipe(uint32_t color, unsigned long duration) {
  unsigned long elapsed = millis() - stateStartMs;
  int lit = (int)((elapsed * runtimePixelCount) / duration);
  if (lit > runtimePixelCount) lit = runtimePixelCount;
  for (uint16_t i = 0; i < runtimePixelCount; i++)
    ring.setPixelColor(i, (i < lit) ? color : 0);
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: spinner — rotating segment of width LEDs, period ms per rev
// ---------------------------------------------------------------------------

static void animSpinner(uint32_t color, int width, unsigned long period) {
  unsigned long elapsed = millis() - stateStartMs;
  int head = (int)((elapsed % period) * runtimePixelCount / period);
  ring.clear();
  for (uint16_t i = 0; i < runtimePixelCount; i++) {
    int dist = (head - i + runtimePixelCount) % runtimePixelCount;
    if (dist < width)
      ring.setPixelColor(i, color);
  }
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: flash — solid color for duration ms then revert
// ---------------------------------------------------------------------------

static void animFlash(uint32_t color, unsigned long duration) {
  unsigned long elapsed = millis() - stateStartMs;
  if (elapsed < duration) {
    for (uint16_t i = 0; i < runtimePixelCount; i++) ring.setPixelColor(i, color);
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
  for (uint16_t i = 0; i < runtimePixelCount; i++)
    ring.setPixelColor(i, on ? color : 0);
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: chase — theater-chase pattern
// ---------------------------------------------------------------------------

static void animChase(uint32_t color, int spacing, unsigned long period) {
  unsigned long elapsed = millis() - stateStartMs;
  int offset = (int)((elapsed % period) * spacing / period);
  ring.clear();
  for (uint16_t i = 0; i < runtimePixelCount; i++) {
    if ((i + offset) % spacing == 0)
      ring.setPixelColor(i, color);
  }
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: breathing — sine-wave brightness (fades to black)
// ---------------------------------------------------------------------------

static void animBreathing(uint32_t color, unsigned long period) {
  unsigned long elapsed = millis() - stateStartMs;
  float bright = sineBrightness(elapsed, period);
  uint32_t scaled = scaleColor(color, bright);
  for (uint16_t i = 0; i < runtimePixelCount; i++) ring.setPixelColor(i, scaled);
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation: pulse — sine-wave with raised floor (never fully dark)
// ---------------------------------------------------------------------------

static void animPulse(uint32_t color, unsigned long period) {
  unsigned long elapsed = millis() - stateStartMs;
  float bright = sineBrightness(elapsed, period);
  bright = 0.15f + bright * 0.85f;
  uint32_t scaled = scaleColor(color, bright);
  for (uint16_t i = 0; i < runtimePixelCount; i++) ring.setPixelColor(i, scaled);
  ring.show();
}

// ---------------------------------------------------------------------------
// Animation dispatcher — parameters match CircuitPython STATE_MAP exactly
// ---------------------------------------------------------------------------

static void animate() {
  switch (currentState) {
    case ST_OFF:
    case ST_IDLE:
      animOff();
      break;
    case ST_SESSION_START:
      animWipe(COL_SESSION_START, 800);
      break;
    case ST_PROMPT_SUBMITTED:
      animWipe(COL_PROMPT, 800);
      break;
    case ST_WORKING:
      animSpinner(COL_WORKING, 6, 1000);
      break;
    case ST_TOOL_OK:
      animFlash(COL_TOOL_OK, 300);
      break;
    case ST_TOOL_ERROR:
      animFlash(COL_TOOL_ERROR, 300);
      break;
    case ST_TOOL_DENIED:
      animFlash(COL_TOOL_DENIED, 300);
      break;
    case ST_AWAITING_PERMISSION:
      animBlink(COL_PERMISSION, 600);
      break;
    case ST_AWAITING_ELICITATION:
      animPulse(COL_ELICITATION, 1500);
      break;
    case ST_SUBAGENT_ACTIVE:
      animChase(COL_SUBAGENT, 4, 1000);
      break;
    case ST_AGENT_IDLE:
      animBreathing(COL_AGENT_IDLE, 3000);
      break;
    case ST_COMPACTING:
      animWipe(COL_COMPACTING, 800);
      break;
    case ST_ERROR:
      animFlash(COL_ERROR, 800);
      break;
    case ST_NOTIFY:
      animFlash(COL_NOTIFY, 300);
      break;
    default:
      animOff();
      break;
  }
}

// ---------------------------------------------------------------------------
// Arduino entry points
// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(SERIAL_BAUD);
  ring.begin();
  ring.setBrightness(runtimeBrightness);

  // Startup animation — magenta wipe to confirm the ring is alive
  for (uint16_t i = 0; i < runtimePixelCount; i++) {
    ring.setPixelColor(i, COL_WORKING);
    ring.show();
    delay(20);
  }
  delay(300);
  ring.clear();
  ring.show();

  // Initialize session entries
  for (uint8_t i = 0; i < MAX_SESSIONS; i++)
    sessions[i].occupied = false;

  lastRxMs = millis();

#if HAS_WATCHDOG
  wdtInit(WATCHDOG_MS);
#endif
}

void loop() {
  uint32_t now = millis();

  readSerial();

  if (rsParsedAny) lastRxMs = now;

  // Session-tagged messages clear legacy bare state
  if (rsHasSession) {
    legacyBareValid = false;
  } else if (rsHasBare && !isTransient(rsLatestBare)) {
    legacyBareState = rsLatestBare;
    legacyBareValid = true;
  }

  // Resolve display state — mirrors CircuitPython main loop exactly
  if (rsHasSession || sessionCount > 0) {
    ResolveResult r = trackerResolve(now);
    setState(r.winning);
    if (r.hasTransient && shouldApplyTransient(r.winning, r.transient))
      setState(r.transient);
  } else if (legacyBareValid) {
    setState(legacyBareState);
    if (rsHasBare && isTransient(rsLatestBare)
        && shouldApplyTransient(legacyBareState, rsLatestBare))
      setState(rsLatestBare);
  } else if (rsHasBare && isTransient(rsLatestBare)) {
    // Legacy transient with no persistent bare state
    if (shouldApplyTransient(currentState, rsLatestBare))
      setState(rsLatestBare);
  } else if (staleIdle && sessionCount == 0) {
    ResolveResult r = trackerResolve(now);
    setState(r.winning);
    if (r.hasTransient && shouldApplyTransient(r.winning, r.transient))
      setState(r.transient);
  }

  animate();

  // Serial silence watchdog: reset if active sessions but no serial data
  if (sessionCount > 0 && (now - lastRxMs) > SERIAL_SILENCE_MS)
    softReset();

  // Persistent parse failures: reset to recover
  if (consecutiveErrors >= MAX_CONSEC_ERRORS)
    softReset();

#if HAS_WATCHDOG
  wdtFeed();
#endif

  delay(LOOP_DELAY_MS);
}
