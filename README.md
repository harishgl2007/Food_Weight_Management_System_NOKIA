# Smart Waste Bin Weight Monitoring System

## Documentation

---

# Overview

This program continuously measures the weight of waste inside a smart dustbin using an **HX711 load cell amplifier** connected to a **Raspberry Pi**.

The software automatically:

* Calibrates the empty dustbin during startup.
* Continuously monitors the weight.
* Filters vibrations and unstable readings.
* Detects only significant changes.
* Calculates cumulative waste added.
* Sends the data securely to the cloud over WebSocket.

---

# System Architecture

```
Load Cell
     │
     ▼
HX711 Amplifier
     │
GPIO (17,27)
     │
     ▼
Raspberry Pi
     │
Weight Processing
     │
Noise Filtering
     │
Delta Detection
     │
WebSocket
     │
     ▼
Cloud Server
```

---

# Program Flow

```
Start Program
      │
      ▼
Initialize GPIO
      │
      ▼
Initialize HX711
      │
      ▼
Auto Offset Calibration
(Empty Bin)
      │
      ▼
Connect to Cloud
(WebSocket)
      │
      ▼
Read Weight Forever
      │
      ▼
Filter Noise
      │
      ▼
Detect Significant Change
      │
      ▼
Confirm Reading
      │
      ▼
Send Increment & Total Weight
```

---

# Startup Procedure

## Step 1: Empty the Dustbin

Before starting the program:

* Remove **all waste** from the dustbin.
* Keep **only the dustbin itself** on the load cell.
* Ensure nobody is touching or moving the bin.

This is extremely important because the software uses the current weight as the **zero reference (OFFSET).**

If waste is present during startup, every future reading will be incorrect.

---

## Step 2: Run the Program

Start the application:

```bash
python3 kaka97.py
```

The console will display something similar to:

```
Load cell initialized

=== STARTUP CALIBRATION ===

Ensure EMPTY dustbin is installed.

Calibrating offset...

OFFSET = -1001945
```

The program takes **101 readings** and calculates the **median** value.

Using the median instead of the average helps eliminate electrical noise and sudden spikes.

---

## Step 3: Automatic Monitoring

Once calibration finishes, the program automatically:

* Connects to the cloud
* Starts monitoring the load cell
* Detects changes
* Sends updates whenever required

No further user interaction is required.

---

# How Offset Calibration Works

During startup:

```python
for _ in range(101):
    values.append(hx.read_long())
```

101 raw readings are collected.

After sorting:

```python
values.sort()
offset = values[len(values)//2]
```

The middle value (median) becomes the system OFFSET.

Every future weight is calculated relative to this value.

```
Weight = (Raw Reading - OFFSET)
/ Calibration Factor
```

---

# Weight Calculation

The HX711 produces raw ADC values.

These are converted into grams using:

```python
weight =
(raw - OFFSET)
/ CAL_FACTOR
```

where

* OFFSET = Empty bin reading
* CAL_FACTOR = Calibration constant

Current calibration factor:

```
24.951836734693877
```

---

# Noise Filtering

Tiny vibrations occur due to:

* Wind
* Table vibrations
* Electrical noise
* People touching the dustbin

These are ignored.

```python
NOISE_THRESHOLD = 10
```

If weight changes less than **10 grams**, nothing happens.

Example:

```
Previous = 1000 g

Current = 1006 g

Difference = 6 g

Ignored
```

---

# Significant Change Detection

Only meaningful weight changes are processed.

```python
DELTA_THRESHOLD = 50
```

This means:

The system only reacts if the weight changes by **50 grams or more**.

Example:

```
Previous = 1000 g

Current = 1035 g

Difference = 35 g

Ignored
```

Example:

```
Previous = 1000 g

Current = 1065 g

Difference = 65 g

Processed
```

This prevents unnecessary cloud updates caused by very small changes.

---

# Confirmation of Large Changes

Large jumps can occasionally occur due to electrical interference.

Whenever the detected change exceeds the threshold, the program waits briefly and takes another reading:

```python
await asyncio.sleep(0.2)
```

If the second reading differs too much:

```python
CONFIRM_THRESHOLD = 100
```

the reading is rejected.

Example:

```
1000 g

↓

1450 g

↓

1012 g
```

This is recognized as a false spike and discarded.

---

# Cumulative Weight

Every accepted increase or decrease updates the running total.

Example:

| Event          | Weight | Delta  | Total |
| -------------- | ------ | ------ | ----- |
| Empty          | 0 g    | —      | 0 g   |
| Bottle         | 250 g  | +250 g | 250 g |
| Paper          | 100 g  | +100 g | 350 g |
| Bottle Removed | -250 g | -250 g | 100 g |

Negative totals are never allowed.

---

# Cloud Communication

After a valid change, the Raspberry Pi sends:

```json
{
    "type":"sensor_data",
    "increment":120,
    "cumulative_weight":480
}
```

Where:

* **increment** – Change in weight since the last valid update.
* **cumulative_weight** – Total weight currently recorded in the dustbin.

---

# Automatic Reconnection

If the network disconnects:

```
WebSocket Lost
        │
        ▼
Reconnect
        │
        ▼
Continue Sending
```

The program automatically retries every **5 seconds** until the server becomes available.

No manual restart is required.

---

# Running as a System Service

To ensure the program starts automatically whenever the Raspberry Pi boots, it is recommended to run it as a **systemd service**.

### Example Service File

Create:

```bash
sudo nano /etc/systemd/system/waste-monitor.service
```

Example configuration:

```ini
[Unit]
Description=Smart Waste Bin Monitor
After=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Desktop
ExecStart=/usr/bin/python3 /home/pi/Desktop/kaka97.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Reload systemd:

```bash
sudo systemctl daemon-reload
```

Enable the service:

```bash
sudo systemctl enable waste-monitor.service
```

Start it:

```bash
sudo systemctl start waste-monitor.service
```

Check its status:

```bash
sudo systemctl status waste-monitor.service
```

View live logs:

```bash
journalctl -u waste-monitor.service -f
```

> **Important:** Before powering on or restarting the Raspberry Pi, ensure the dustbin is empty so the startup calibration uses the correct offset.

---

# Configurable Parameters

All important thresholds are defined near the top of the code.

```python
NOISE_THRESHOLD = 10.0
DELTA_THRESHOLD = 50.0
CONFIRM_THRESHOLD = 100.0
CAL_FACTOR = 24.951836734693877
```

### `NOISE_THRESHOLD`

Minimum change ignored by the system.

Current:

```
10 g
```

---

### `DELTA_THRESHOLD`

Minimum weight change required before data is sent to the cloud.

Current:

```
50 g
```

For example:

```python
DELTA_THRESHOLD = 50.0
```

Changing this value changes the cloud reporting sensitivity:

* `25` → More sensitive, reports smaller waste additions.
* `50` → Balanced (recommended).
* `100` → Reports only larger waste additions, reducing cloud traffic.

---

### `CONFIRM_THRESHOLD`

Maximum allowed difference between the first and confirmation readings before rejecting the change as a spike.

Current:

```
100 g
```

Increase it if your load cell is stable and you expect rapid large changes; decrease it if you want stricter spike filtering.

---

### `CAL_FACTOR`

Converts the HX711 raw ADC values into grams.

This value should only be changed after recalibrating the load cell with a known reference weight.

---
