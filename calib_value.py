from hx711 import HX711
import RPi.GPIO as GPIO
import time

DT_PIN = 17
SCK_PIN = 27


def setup():
    GPIO.setmode(GPIO.BCM)

    hx = HX711(DT_PIN, SCK_PIN)
    hx.set_reading_format("MSB", "MSB")

    return hx


def get_raw(hx):

    values = []

    # 15 median readings
    for _ in range(15):
        values.append(hx.read_median(15))
        time.sleep(0.02)

    values.sort()

    # Trim highest & lowest 3
    values = values[3:-3]

    return sum(values) / len(values)


try:

    hx = setup()

    print("\n==============================")
    print(" HX711 Calibration Utility")
    print("==============================")

    print("\n1. Remove ALL weight.")
    input("Press ENTER...")

    offset = get_raw(hx)

    print(f"\nOffset = {offset:.0f}")

    known_weight = float(
        input("\nEnter known weight (grams): ")
    )

    print(f"\n2. Place {known_weight} g on the scale.")
    input("Press ENTER...")

    loaded = get_raw(hx)

    print(f"\nLoaded Raw = {loaded:.0f}")

    # Detect polarity automatically
    if loaded > offset:
        cal = (loaded - offset) / known_weight
    else:
        cal = (offset - loaded) / known_weight

    print("\n==============================")
    print("COPY THESE VALUES")
    print("==============================")

    print(f"OFFSET = {int(offset)}")
    print(f"CAL_FACTOR = {cal}")

    print("\nVerification")

    while True:

        raw = get_raw(hx)

        if loaded > offset:
            weight = (raw - offset) / cal
        else:
            weight = (offset - raw) / cal

        if weight < 0:
            weight = 0

        print(
            f"\rRaw: {int(raw):10d} | "
            f"Weight: {weight:8.2f} g",
            end=""
        )

        time.sleep(0.1)

except KeyboardInterrupt:

    print("\nStopped")

finally:

    GPIO.cleanup()