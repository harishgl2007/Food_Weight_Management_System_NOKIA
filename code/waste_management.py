from waste_management.code.hx711 import HX711
import RPi.GPIO as GPIO
import asyncio
import websockets
import json
import ssl

# ---------------- CONFIG ----------------

DT_PIN = 17
SCK_PIN = 27

WS_URI = "wss://10.129.216.229:5000/ws"

OFFSET = None
CAL_FACTOR = None
ws = None


# ---------------- HX711 ----------------

def setup_load_cell():
    GPIO.setmode(GPIO.BCM)

    hx = HX711(DT_PIN, SCK_PIN)
    hx.set_reading_format("MSB", "MSB")

    print("Load cell initialized")

    return hx


def get_average_raw(hx, samples=20):
    readings = []

    for _ in range(samples):
        readings.append(hx.read_long())

    readings.sort()

    # Median is more resistant to noise
    return readings[len(readings) // 2]


# ---------------- CALIBRATION ----------------

def auto_calibrate(hx):
    print("\n=== CALIBRATION ===")

    print("Remove all weight from the scale.")
    input("Press Enter when ready...")

    offset = get_average_raw(hx, 21)

    print(f"OFFSET = {offset}")

    known_weight = float(
        input("Enter calibration weight (grams): ")
    )

    print(
        f"Place {known_weight} g on the scale."
    )

    input("Press Enter when ready...")

    weighted_raw = get_average_raw(hx, 21)

    cal_factor = (
        weighted_raw - offset
    ) / known_weight

    print(f"CAL_FACTOR = {cal_factor}")

    return offset, cal_factor


# ---------------- WEIGHT ----------------

def get_weight(hx):
    raw = get_average_raw(hx, 11)

    weight = (raw - OFFSET) / CAL_FACTOR

    # Handle reversed polarity
    if weight < 0:
        weight = -weight

    return round(weight, 2), raw


# ---------------- WEBSOCKET ----------------

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


async def send_weight(weight, raw):
    global ws

    payload = {
        "type": "sensor_data",
        "weight_g": weight,
        "raw": raw
    }

    try:
        await ws.send(json.dumps(payload))

        print("Sent:", payload)

    except Exception as e:
        print("Send error:", e)

        await connect_websocket()


# ---------------- MAIN LOOP ----------------

async def read_loop(hx):
    while True:
        try:
            weight, raw = get_weight(hx)

            print(
                f"Raw: {raw} | "
                f"Weight: {weight:.2f} g"
            )

            await send_weight(weight, raw)

            await asyncio.sleep(0.5)

        except Exception as e:
            print("Read error:", e)
            await asyncio.sleep(1)


# ---------------- MAIN ----------------

async def main():
    global OFFSET
    global CAL_FACTOR

    hx = setup_load_cell()

    OFFSET, CAL_FACTOR = auto_calibrate(hx)

    print(
        f"\nUsing OFFSET={OFFSET}"
        f"\nUsing CAL_FACTOR={CAL_FACTOR}"
    )

    await connect_websocket()

    try:
        await read_loop(hx)

    finally:
        GPIO.cleanup()

        if ws:
            await ws.close()

        print("GPIO cleaned up")


if __name__ == "__main__":
    asyncio.run(main())