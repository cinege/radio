Raspberry Pi Internet Radio

Ez a projekt egy headless Raspberry Pi alapú internet rádió, amely:
mpv-t használ lejátszásra (IPC socketen vezérelve)
GPIO gombbal csatornát vált és kikapcsol
HTTP API-n keresztül vezérelhető (Android app)
watchdoggal felügyeli a stream állapotát
induláskor lágy hangerő-felfutást alkalmaz
systemd service-ként fut

Követelmények

Hardver

Raspberry Pi (tested: Pi 3 / Pi 4)
USB audio kártya vagy DAC
Nyomógomb (GPIO)
Internet kapcsolat

Szoftver

Raspberry Pi OS (Bookworm / Bullseye)
Python 3.9+
mpv
ALSA
gpiozero

ALSA konfiguráció (kritikus)

A projekt feltételezi, hogy az alapértelmezett ALSA kimenet nem a HDMI, hanem egy külső USB audio eszköz.
Ezért szükséges egy .asoundrc fájl a felhasználó home könyvtárában:

nano ~/.asoundrc

Tartalma:

pcm.!default {
    type plug
    slave {
        pcm "hw:1,0"
    }
}

ctl.!default {
    type hw
    card 1
}

Megjegyzések

hw:1,0 → az USB audio eszköz

Ellenőrzéshez:

aplay -l


Ha más kártyaszámot kapsz, módosítsd ennek megfelelően

Ez a lépés elengedhetetlen, különben systemd alatt az mpv „némán” indul.

Könyvtárstruktúra
/home/pi/radio/
├── radio.py
├── stations.txt
├── status.txt
├── radio.log

stations.txt formátum
Kossuth Rádió,https://...
Petőfi Rádió,https://...

Függőségek telepítése
sudo apt update
sudo apt install -y \
    mpv \
    python3-gpiozero \
    alsa-utils

Python script futtatása (teszt)
cd /home/pi/radio
python3 radio.py


Ellenőrizd:

van hang

gomb működik

http://<pi-ip>:8080/status válaszol

Systemd service létrehozása (ajánlott)
/etc/systemd/system/radio.service
[Unit]
Description=Raspberry Pi Radio
After=network.target sound.target

[Service]
User=pi
WorkingDirectory=/home/pi/radio
ExecStart=/usr/bin/python3 /home/pi/radio/radio.py
Restart=always
RestartSec=5
Environment=HOME=/home/pi

[Install]
WantedBy=multi-user.target


Aktiválás:

sudo systemctl daemon-reload
sudo systemctl enable radio
sudo systemctl start radio


Állapot:

sudo systemctl status radio

Jogosultságok (leállítás / újraindítás)

A rádió nem rootként fut, ezért célzott sudo jogosultság szükséges.

sudo visudo -f /etc/sudoers.d/radio


Tartalom:

pi ALL=(root) NOPASSWD: /sbin/shutdown, /sbin/reboot


A Python kódban:

os.system("sudo /sbin/shutdown -h now")
os.system("sudo /sbin/reboot")

HTTP API
POST

0..N → csatornaváltás

volume:NN → hangerő (azonnali)

100 → shutdown

200 → reboot

GET

/ → aktuális csatorna index

/status → JSON státusz

Példa:

{
  "name": "Kossuth Rádió",
  "volume": 58
}

Megjegyzések

Induláskor a hangerő 30 → 60% között lágyan felfut

POST hangerőváltás nem fade-el (szándékos)

mpv IPC socket: /tmp/mpv-radio.sock

Known issues / TODO

fade-out leállításkor

hangerő mentése reboot előtt

Wi-Fi reconnect figyelés

Android app API versioning
