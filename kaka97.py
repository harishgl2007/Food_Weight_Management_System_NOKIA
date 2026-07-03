from waste_management.code.hx711 import HX711
import RPi.GPIO as GPIO
import asyncio
import websockets
import json
import ssl

# ---------------- CONFIG ---------------


DT_PIN = 17
SCK_PIN = 27

# Keep this fixed after calibration
CAL_FACTOR = 24.951836734693877

# WebSocket
WS_URI = "wss://10.129.216.229:5000/ws"

# Thresholds
NOISE_THRESHOLD = 10.0       # Ignore tiny vibrations
DELTA_THRESHOLD = 50.0       # Significant change
CONFIRM_THRESHOLD = 100.0    # Confirmation tolerance

# ---------------- GLOBALS ----------------

OFFSET = None
ws = None

previous_weight = 0.0
cumulative_weight = 0.0


# --------------------------------------------------
# HX711 SETUP
# --------------------------------------------------

def setup_load_cell():
    GPIO.setmode(GPIO.BCM)

    hx = HX711(DT_PIN, SCK_PIN)
    hx.set_reading_format("MSB", "MSB")

    print("Load cell initialized")

    return hx


# --------------------------------------------------
# STARTUP OFFSET CALIBRATION
# --------------------------------------------------

def auto_calibrate_offset(hx):

    print("\n=== STARTUP CALIBRATION ===")
    print("Ensure EMPTY dustbin is installed.")
    print("Calibrating offset...")

    values = []

    for _ in range(101):
        values.append(hx.read_long())

    values.sort()

    offset = values[len(values) // 2]

    print(f"OFFSET = {offset}")

    return offset


# --------------------------------------------------
# WEIGHT CALCULATION
# --------------------------------------------------

def get_weight(hx):
    global OFFSET

    raw = hx.read_median(11)

    weight = (raw - OFFSET) / CAL_FACTOR

    if weight < 0:
        weight = 0

    return round(weight, 2)


# --------------------------------------------------
# WEBSOCKET
# --------------------------------------------------

async def connect_websocket():
    global ws

    while True:

        try:

            ssl_context = ssl.SSLContext(
                ssl.PROTOCOL_TLS_CLIENT
            )

            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            print(f"Connecting to {WS_URI}")

            ws = await websockets.connect(
                WS_URI,
                ssl=ssl_context,
                ping_interval=20,
                ping_timeout=20
            )

            print("WebSocket connected")

            return

        except Exception as e:

            print("Connection failed:", e)

            await asyncio.sleep(5)


async def send_weight(increment, cumulative):
    global ws

    payload = {
        "type": "sensor_data",
        "increment": round(increment, 2),
        "cumulative_weight": round(cumulative, 2)
    }

    try:

        await ws.send(json.dumps(payload))

        print("Sent:", payload)

    except Exception as e:

        print("Send error:", e)

        try:

            await connect_websocket()

            await ws.send(json.dumps(payload))

            print(
                "Sent after reconnect:",
                payload
            )

        except Exception as e2:

            print(
                "Reconnect failed:",
                e2
            )


# --------------------------------------------------
# MAIN LOOP
# --------------------------------------------------

async def read_loop(hx):

    global previous_weight
    global cumulative_weight

    while True:

        try:

            weight = get_weight(hx)

            delta = weight - previous_weight

            # -----------------------------
            # Confirm large changes
            # -----------------------------

            if abs(delta) >= DELTA_THRESHOLD:

                await asyncio.sleep(0.2)

                confirm_weight = get_weight(hx)

                if abs(
                    confirm_weight - weight
                ) > CONFIRM_THRESHOLD:

                    print(
                        f"Rejected spike: "
                        f"{weight:.1f}g -> "
                        f"{confirm_weight:.1f}g"
                    )

                    await asyncio.sleep(0.3)

                    continue

                weight = confirm_weight
                delta = weight - previous_weight

            print(
                f"Weight={weight:.2f}g "
                f"Delta={delta:.2f}g"
            )

            # Ignore tiny noise

            if abs(delta) < NOISE_THRESHOLD:

                await asyncio.sleep(0.5)

                continue

            # Valid change

            if abs(delta) >= DELTA_THRESHOLD:

                cumulative_weight += delta

                if cumulative_weight < 0:
                    cumulative_weight = 0

                await send_weight(
                    delta,
                    cumulative_weight
                )

                previous_weight = weight

            await asyncio.sleep(0.5)

        except Exception as e:

            print("Read error:", e)

            await asyncio.sleep(1)


# --------------------------------------------------
# MAIN
# --------------------------------------------------

async def main():

    global OFFSET

    hx = setup_load_cell()

    OFFSET = auto_calibrate_offset(hx)

    print(
        f"Using OFFSET={OFFSET}, "
        f"CAL_FACTOR={CAL_FACTOR}"
    )

    await connect_websocket()

    try:

        await read_loop(hx)
        raw = hx.read_median(21)
        print(raw)

    finally:

        GPIO.cleanup()

        if ws:
            await ws.close()

        print("GPIO cleaned up")


if __name__ == "__main__":
    asyncio.run(main())
