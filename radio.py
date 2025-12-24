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
                    "--volume=30",  # kezdő hangerő 30%
                    "--input-ipc-server=" + MPV_SOCKET,
                    url
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            self.last_ok = time.time()

            # fade-in 50 -> 80%
            def fade_in():
                current_volume = 50
                target_volume = 90
                step = 1
                interval = 0.2

                # várakozás, amíg létrejön a socket (max 5 sec)
                waited = 0
                while not os.path.exists(MPV_SOCKET) and waited < 5:
                    time.sleep(0.1)
                    waited += 0.1

                while current_volume < target_volume and self.is_running():
                    self.set_volume(current_volume)
                    current_volume += step
                    time.sleep(interval)

            threading.Thread(target=fade_in, daemon=True).start()

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

    def stream_healthy(self):
        playback_time = self.mpv_property("playback-time")
        eof = self.mpv_property("eof-reached")
        paused = self.mpv_property("pause")

        if playback_time is None or bool(eof) or bool(paused):
            return False

        self.last_ok = time.time()
        return True

    def get_volume(self):
        vol = self.mpv_property("volume")
        if vol is None:
            return 50
        return int(vol)

    def set_volume(self, vol: int):
        try:
            with socket.socket(socket.AF_UNIX) as s:
                s.connect(MPV_SOCKET)
                s.sendall(json.dumps({
                    "command": ["set_property", "volume", vol]
                }).encode() + b"\n")
            logging.info(f"Volume set to {vol}")
            return True
        except Exception as e:
            logging.error(f"Failed to set volume: {e}")
            return False

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
                continue

            if not self.player.stream_healthy():
                logging.warning("Stream unhealthy")
                if time.time() - self.player.last_ok > self.timeout:
                    logging.error("Stream stalled – restarting")
                    self.player.restart()

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            self.handle_status()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(str(self.server.station_manager.index).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        msg = self.rfile.read(length).decode('utf-8').strip()

        logging.info(f"POST received: {msg}")

        if msg == "100":
            os.system("sudo shutdown -h now")
        elif msg == "200":
            os.system("sudo shutdown -r now")
        elif msg.isdigit():
            idx = int(msg)
            self.server.station_manager.set(idx)
            self.server.player.restart()
        elif msg.startswith("volume:"):
            try:
                vol = int(msg.split(":",1)[1])
                self.server.player.set_volume(vol)
            except Exception as e:
                logging.error(f"Invalid volume value: {msg} ({e})")

        self.send_response(200)
        self.end_headers()

    def handle_status(self):
        station_manager = self.server.station_manager
        player = self.server.player

        index = station_manager.index
        name, url = station_manager.stations[index].split(",", 1)
        volume = player.get_volume()

        status = {
            "name": name,
            "volume": volume
        }

        response = json.dumps(status).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

class RadioHTTPServer(HTTPServer):
    def __init__(self, addr, handler, station_manager, player):
        super().__init__(addr, handler)
        self.station_manager = station_manager
        self.player = player

def main():
    os.makedirs(BASE_DIR, exist_ok=True)

    station_manager = StationManager(STATIONS_FILE, STATUS_FILE)
    player = RadioPlayer(station_manager)
    player.start()

    watchdog = Watchdog(player, WATCHDOG_TIMEOUT)
    watchdog.start()

    # GPIO button – fő szálban
    gpio_button = Button(pin=14, hold_time=2)
    gpio_button.when_pressed = lambda: (logging.info("GPIO short press"), station_manager.next(), player.restart())
    gpio_button.when_held = lambda: (logging.warning("GPIO long press – shutdown"), os.system("sudo shutdown -h now"))
    logging.info("GPIO button initialized")

    server = RadioHTTPServer(
        ("", HTTP_PORT),
        RequestHandler,
        station_manager,
        player
    )

    logging.info("Radio server started")

    # a HTTP server külön szálon
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # blokkoljuk a fő szálat a GPIO eseményekhez
    pause()

if __name__ == "__main__":
    main()
