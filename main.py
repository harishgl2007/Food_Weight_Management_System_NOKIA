from hx711 import HX711
import RPi.GPIO as GPIO
import asyncio
import websockets
import json
import ssl

# ---------------- CONFIG ----------------

DT_PIN = 17
SCK_PIN = 27

WS_URI = "wss://10.129.216.229:5000/ws"

# FIXED CALIBRATION (your values)
OFFSET = -1001945
CAL_FACTOR = 18.232463295269167

ws = None

# ---------------- HX711 ----------------

def setup_load_cell():

    GPIO.setmode(GPIO.BCM)

    hx = HX711(DT_PIN, SCK_PIN)
    hx.set_reading_format("MSB", "MSB")

    print("HX711 ready")

    return hx


# ---------------- FILTER (RAW DOMAIN) ----------------

class RawFilter:

    def __init__(self):

        self.filtered = None
        self.last_raw = None

        self.SPIKE_LIMIT = 8000   # raw ADC jump rejection

        self.FAST_ALPHA = 0.35
        self.SLOW_ALPHA = 0.08

    def update(self, raw):

        # reject impossible spikes
        if self.last_raw is not None:
            if abs(raw - self.last_raw) > self.SPIKE_LIMIT:
                raw = self.last_raw

        self.last_raw = raw

        # init
        if self.filtered is None:
            self.filtered = raw
            return int(self.filtered)

        diff = abs(raw - self.filtered)

        if diff > 5000:
            alpha = self.FAST_ALPHA
        else:
            alpha = self.SLOW_ALPHA

        self.filtered += alpha * (raw - self.filtered)

        return int(self.filtered)


# ---------------- WEIGHT ----------------

def convert_weight(raw):

    weight = (raw - OFFSET) / CAL_FACTOR

    if weight < 0:
        weight = 0

    return round(weight, 2)


def read_raw(hx):

    samples = []

    for _ in range(3):
        samples.append(hx.read_median(7))

    samples.sort()

    return samples[1]   # median of 3 medians


# ---------------- WEBSOCKET ----------------

async def connect():

    global ws

    while True:

        try:

            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            ws = await websockets.connect(
                WS_URI,
                ssl=ctx,
                ping_interval=20,
                ping_timeout=20
            )

            print("Connected")

            return

        except Exception as e:

            print("Connection failed:", e)

            await asyncio.sleep(5)


async def send_packet(weight, raw):

    global ws

    msg = {
        "type": "sensor_data",
        "increment": round(weight, 2),
        "cumulative_weight": round(weight, 2)
    }

    try:

        await ws.send(json.dumps(msg))

    except Exception as e:

        print("Send error:", e)

        await connect()

        await ws.send(json.dumps(msg))


# ---------------- LOOP ----------------

async def loop(hx):

    filt = RawFilter()

    while True:

        raw = read_raw(hx)

        raw = filt.update(raw)

        weight = convert_weight(raw)

        print(
            f"\rRaw:{raw:10d} | "
            f"Weight:{weight:8.2f} g",
            end=""
        )

        await send_packet(weight, raw)

        await asyncio.sleep(0.5)


# ---------------- MAIN ----------------

async def main():

    hx = setup_load_cell()

    print(f"OFFSET={OFFSET}")
    print(f"CAL_FACTOR={CAL_FACTOR}")

    await connect()

    try:

        await loop(hx)

    finally:

        GPIO.cleanup()

        if ws:
            await ws.close()

        print("\nStopped")


if __name__ == "__main__":
    asyncio.run(main()) 