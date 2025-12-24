#!/usr/bin/env python3

import os
import time
import threading
import subprocess
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from gpiozero import Button
from signal import pause
import json
import socket

BASE_DIR = "/home/pi/radio"
STATIONS_FILE = f"{BASE_DIR}/stations.txt"
STATUS_FILE = f"{BASE_DIR}/status.txt"
LOG_FILE = f"{BASE_DIR}/radio.log"
MPV_SOCKET = "/tmp/mpv-radio.sock"

HTTP_PORT = 8080
WATCHDOG_TIMEOUT = 180  # 3 perc

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

class StationManager:
    def __init__(self, stations_file, status_file):
        self.stations_file = stations_file
        self.status_file = status_file
        self.stations = self._load_stations()
        self.index = self._load_index()

    def _load_stations(self):
        with open(self.stations_file) as f:
            return [line.strip() for line in f if line.strip()]

    def _load_index(self):
        try:
            with open(self.status_file) as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def save_index(self):
        with open(self.status_file, "w") as f:
            f.write(str(self.index))

    def get_url(self):
        _, url = self.stations[self.index].split(",", 1)
        return url

    def next(self):
        self.index = (self.index + 1) % len(self.stations)
        self.save_index()

    def set(self, index: int):
        if 0 <= index < len(self.stations):
            self.index = index
            self.save_index()

class RadioPlayer:
    def __init__(self, station_manager):
        self.station_manager = station_manager
        self.process = None
        self.last_ok = time.time()
        self.lock = threading.Lock()

    def mpv_property(self, prop):
       try:
           with socket.socket(socket.AF_UNIX) as s:
               s.connect(MPV_SOCKET)
               s.sendall(json.dumps({
                   "command": ["get_property", prop]
               }).encode() + b"\n")
   
               data = s.recv(1024)
               response = json.loads(data.decode())
               return response.get("data")
       except Exception:
           return None

    def start(self):
          with self.lock:
              self.stop()
      
              if os.path.exists(MPV_SOCKET):
                  os.remove(MPV_SOCKET)
      
              url = self.station_manager.get_url()
              logging.info(f"Starting stream: {url}")
      
              self.process = subprocess.Popen(
                  [
                      "mpv",
                      "--no-video",
                      "--audio-device=alsa",
                      "--volume=50",
                      "--input-ipc-server=" + MPV_SOCKET,
                      url
                  ],
                  stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL
              )
      
              self.last_ok = time.time()


    def stop(self):
        if self.process and self.process.poll() is None:
            logging.info("Stopping player")
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def restart(self):
        logging.warning("Restarting stream")
        self.start()

    def is_running(self):
        return self.process and self.process.poll() is None

    

class Watchdog(threading.Thread):
    def __init__(self, player, timeout):
        super().__init__(daemon=True)
        self.player = player
        self.timeout = timeout

    def run(self):
        while True:
            time.sleep(10)
            if not self.player.is_running():
                logging.warning("Player not running")
                self.player.restart()
            elif time.time() - self.player.last_ok > self.timeout:
                logging.warning("Watchdog timeout exceeded")
                self.player.restart()


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(str(self.server.station_manager.index).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        msg = self.rfile.read(length).decode().strip()

        logging.info(f"POST received: {msg}")

        if msg == "100":
            os.system("shutdown -h now")
        elif msg == "200":
            os.system("shutdown -r now")
        elif msg.isdigit():
            idx = int(msg)
            self.server.station_manager.set(idx)
            self.server.player.restart()

        self.send_response(200)
        self.end_headers()

class RadioHTTPServer(HTTPServer):
    def __init__(self, addr, handler, station_manager, player):
        super().__init__(addr, handler)
        self.station_manager = station_manager
        self.player = player

class GPIOHandler(threading.Thread):
    def __init__(self, station_manager, player, pin=17, hold_time=2):
        super().__init__(daemon=True)
        self.station_manager = station_manager
        self.player = player

        self.button = Button(pin, hold_time=hold_time)
        self.button.when_pressed = self.short_press
        self.button.when_held = self.long_press

        logging.info(f"GPIO button initialized on pin {pin}")

    def short_press(self):
        logging.info("GPIO short press")
        self.station_manager.next()
        self.player.restart()

    def long_press(self):
        logging.warning("GPIO long press – shutdown")
        os.system("shutdown -h now")

    def run(self):
        pause()  # eseményvezérelt, nem terheli a CPU-t


def main():
    os.makedirs(BASE_DIR, exist_ok=True)

    station_manager = StationManager(STATIONS_FILE, STATUS_FILE)
    player = RadioPlayer(station_manager)
    player.start()

    watchdog = Watchdog(player, WATCHDOG_TIMEOUT)
    watchdog.start()

    gpio = GPIOHandler(station_manager, player, pin=17, hold_time=2)
    gpio.start()

    server = RadioHTTPServer(
        ("", HTTP_PORT),
        RequestHandler,
        station_manager,
        player
    )

    logging.info("Radio server started")
    server.serve_forever()


if __name__ == "__main__":
    main()

