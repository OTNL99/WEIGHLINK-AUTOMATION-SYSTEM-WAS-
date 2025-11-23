import asyncio
import time
import csv
import os
import json
from datetime import datetime
from threading import Thread, Event

# Google Sheets imports
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Serial and BLE libs
import serial  # pyserial
from bleak import BleakClient, BleakScanner  # bleak for BLE

# CONFIG
GOOGLE_CREDS_FILE = "creds.json"          # Service account JSON
SPREADSHEET_NAME = "Weight_logger"         # Name of your Google Sheet (sheet1)
LOCAL_BUFFER = "buffered_weights.csv"     # local buffer file
POLL_INTERVAL = 1.0                       # seconds between serial reads
BLE_SCAN_TIMEOUT = 5.0

# Bluetooth Serial COM port (if using classic SPP/paired virtual COM on Windows)
SERIAL_PORT = None   # e.g., "COM4" on Windows or "/dev/rfcomm0" on Linux
SERIAL_BAUD = 9600

# BLE config (if using BLE GATT)
BLE_DEVICE_NAME = None    # e.g., "MyScale" OR set BLE_ADDRESS below
BLE_ADDRESS = None        # MAC address or BLE id if known
BLE_WEIGHT_CHAR_UUID = None  # set to the characteristic UUID that contains weight data

# helper: Google Sheets auth
def init_sheets():
    scope = ["https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).sheet1
    return sheet

# append to google sheet (with basic exception handling)
def append_to_sheet(sheet, weight, raw_string=None, metadata=None):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    row = [ts, weight, raw_string or "", json.dumps(metadata or {})]
    try:
        sheet.append_row(row)
        print("Appended to sheet:", row)
        return True
    except Exception as e:
        print("Failed to append to sheet:", e)
        return False

# local buffer write
def buffer_local(weight, raw_string=None, metadata=None):
    write_header = not os.path.exists(LOCAL_BUFFER)
    with open(LOCAL_BUFFER, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["ts_utc","weight","raw","metadata"])
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([ts, weight, raw_string or "", json.dumps(metadata or {})])
    print("Buffered locally:", weight)

# function to flush buffer to sheet
def flush_buffer(sheet):
    if not os.path.exists(LOCAL_BUFFER):
        return
    temp_file = LOCAL_BUFFER + ".tmp"
    try:
        with open(LOCAL_BUFFER, "r", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            rows = list(reader)
        for row in rows:
            try:
                sheet.append_row(row)
            except Exception as e:
                print("Failed to append buffered row:", row, e)
                return  # stop if server rejects, keep file
        # if we reached here, all rows were pushed
        os.remove(LOCAL_BUFFER)
        print("Flushed buffered rows to sheet.")
    except Exception as e:
        print("Buffer flush error:", e)

# parse a weight string to float (robust)
import re
def parse_weight(s):
    if s is None: 
        return None
    s = s.strip()
    # common formats: "123.45", "+00123.45 kg", "ST,GS, +00123.45 kg"
    m = re.search(r"([-+]?\d{1,7}(?:\.\d+)?)", s.replace(",", ""))
    if m:
        try:
            return float(m.group(1))
        except:
            return None
    return None

# Serial reader loop
def serial_reader_loop(stop_event, sheet=None):
    if not SERIAL_PORT:
        print("SERIAL_PORT not configured. Skipping serial reader.")
        return
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)
        print("Opened serial port:", SERIAL_PORT)
    except Exception as e:
        print("Failed to open serial port:", e)
        return
    while not stop_event.is_set():
        try:
            raw = ser.readline().decode(errors='ignore').strip()
            if not raw:
                time.sleep(0.1)
                continue
            weight = parse_weight(raw)
            print("Serial raw:", raw, "=>", weight)
            if weight is not None:
                ok = False
                if sheet:
                    ok = append_to_sheet(sheet, weight, raw, {"source":"serial","port":SERIAL_PORT})
                    if not ok:
                        buffer_local(weight, raw, {"source":"serial"})
                else:
                    buffer_local(weight, raw, {"source":"serial"})
        except Exception as e:
            print("Serial read error:", e)
            time.sleep(1)
    try:
        ser.close()
    except:
        pass

# BLE listener (subscribe / poll)
async def ble_read_and_forward(sheet, stop_event):
    # If BLE_ADDRESS known, try connect directly; otherwise scan
    target = BLE_ADDRESS
    if not target and BLE_DEVICE_NAME:
        print("Scanning for BLE device named:", BLE_DEVICE_NAME)
        devices = await BleakScanner.discover(timeout=BLE_SCAN_TIMEOUT)
        for d in devices:
            if d.name and BLE_DEVICE_NAME in d.name:
                target = d.address
                print("Found address:", target)
                break
    if not target:
        print("No BLE device address found; aborting BLE read.")
        return
    while not stop_event.is_set():
        try:
            async with BleakClient(target) as client:
                print("Connected to BLE", target)
                # read directly if char supports read
                if BLE_WEIGHT_CHAR_UUID:
                    data = await client.read_gatt_char(BLE_WEIGHT_CHAR_UUID)
                    raw = data.decode(errors='ignore')
                    weight = parse_weight(raw)
                    print("BLE read:", raw, "=>", weight)
                    if weight is not None:
                        ok = False
                        if sheet:
                            ok = append_to_sheet(sheet, weight, raw, {"source":"ble","addr":target})
                            if not ok:
                                buffer_local(weight, raw, {"source":"ble"})
                        else:
                            buffer_local(weight, raw, {"source":"ble"})
                else:
                    # Try notify-based approach; subscribe if available
                    # Attempt to find notifiable characteristics
                    for svc in client.services:
                        for char in svc.characteristics:
                            if "notify" in char.properties:
                                def handle(_, data):
                                    raw = bytes(data).decode(errors='ignore')
                                    weight = parse_weight(raw)
                                    print("BLE notify:", raw, "=>", weight)
                                    if weight is not None:
                                        if sheet:
                                            if not append_to_sheet(sheet, weight, raw, {"source":"ble_notify","char":str(char.uuid)}):
                                                buffer_local(weight, raw, {"source":"ble_notify"})
                                        else:
                                            buffer_local(weight, raw, {"source":"ble_notify"})
                                await client.start_notify(char.uuid, handle)
                    # wait while connected
                    while client.is_connected and not stop_event.is_set():
                        await asyncio.sleep(1)
        except Exception as e:
            print("BLE connect/read error:", e)
            await asyncio.sleep(2)

# main
def main():
    stop_event = Event()
    sheet = None
    # init sheets if creds present
    if os.path.exists(GOOGLE_CREDS_FILE):
        try:
            sheet = init_sheets()
            print("Connected to Google Sheet:", SPREADSHEET_NAME)
            # try flush on start
            flush_buffer(sheet)
        except Exception as e:
            print("Google Sheets init failed:", e)
            sheet = None
    else:
        print("Google creds not found; running in buffer-only mode.")

    # start serial thread if port configured
    serial_thread = None
    if SERIAL_PORT:
        serial_thread = Thread(target=serial_reader_loop, args=(stop_event, sheet), daemon=True)
        serial_thread.start()

    # start BLE loop in background event loop if configured
    import asyncio
    ble_task = None
    if BLE_DEVICE_NAME or BLE_ADDRESS:
        loop = asyncio.get_event_loop()
        ble_task = loop.create_task(ble_read_and_forward(sheet, stop_event))

    print("Gateway running. Ctrl+C to stop.")
    try:
        if ble_task:
            loop.run_forever()
        else:
            # just wait while serial thread runs
            while True:
                time.sleep(1)
                # if sheet was None and creds now available, try to init
                if sheet is None and os.path.exists(GOOGLE_CREDS_FILE):
                    try:
                        sheet = init_sheets()
                        print("Late-connected to Google Sheet.")
                        flush_buffer(sheet)
                    except Exception as e:
                        print("Late Google Sheets init failed:", e)
    except KeyboardInterrupt:
        print("Stopping...")
        stop_event.set()
        if serial_thread:
            serial_thread.join(timeout=2)
        if ble_task:
            ble_task.cancel()
    except Exception as e:
        print("Runtime error:", e)
    print("Exited.")

if __name__ == "__main__":
    main()
