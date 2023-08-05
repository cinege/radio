#!/usr/bin/python

import sys, traceback
sys.stdout = open('/home/pi/radio/radio.log', 'a')
sys.stderr = open('/home/pi/radio/error.log', 'a')
import RPi.GPIO as GPIO
import time, os, datetime
from datetime import timedelta
import subprocess, alsaaudio

##################################################
#################  Constants  ####################
##################################################
pin = 14
stationcount = 6
#mplayercall = "mplayer -fs ffmpeg://"
m = alsaaudio.Mixer("PCM")

##################################################
################# Subroutines ####################
##################################################

def log(message):
   print(datetime.datetime.now().strftime("%m.%d %H:%M:%S") + " " + message)

def getfirstradioindex():
   with open('/home/pi/radio/status.txt', 'r') as f:
      try:
         lines = f.readlines()
         startindex = lines[0]
      except:
         startindex = "0" 
   return int(startindex)

def writeradiostatus(index):
   with open('/home/pi/radio/status.txt', 'w') as f:
      f.write(str(index % stationcount))

def getradio(index):
   with open('/home/pi/radio/stations.txt', 'r') as f:
      stations = f.readlines()
      radiourl = stations[index % stationcount].replace("\n","")
   return radiourl

def startradio(url):
   urlparts = url.split(",")
   log("starting radio: " + urlparts[0])
   m.setvolume(0)
   #p = subprocess.Popen(["mplayer", url], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
   p = subprocess.Popen(["mplayer", urlparts[1], urlparts[2]])
   time.sleep(1.2)
   for i in range(20):
      m.setvolume(i*5)
      time.sleep(0.1)
   return p

def killradio(proc):
   try:
      proc.kill()
      time.sleep(1)
   except:
      log("nem sikerult a process lezarasa")
   os.system("pkill -9 mplayer")
   time.sleep(1)

##################################################
################# Program start ##################
##################################################

log("elindult")

GPIO.setmode(GPIO.BCM)
GPIO.setup(pin,GPIO.IN,pull_up_down=GPIO.PUD_UP)

timestamp_old = datetime.datetime.now()
radio = getfirstradioindex()

url = getradio(radio)
p = startradio(url)
while True: #infinite loop
   if GPIO.input(pin) == 0: #ranyomott
        kilep = False
        time.sleep(1.3)
        for i in range(10):
           if GPIO.input(pin) == 0:
              kilep = True
              break
           time.sleep(0.1)
        timestamp = datetime.datetime.now()
        delta = (timestamp - timestamp_old).seconds
        print (delta)
        if not kilep:
           radio += 1
           writeradiostatus(radio)
           url = getradio(radio)
           killradio(p)
           p = startradio(url)
           log("started " + url)
           timestamp_old = timestamp
           time.sleep(0.5) # varj 0.5 masodpercet 
        else:
           log("Shutdown signal")
           GPIO.cleanup()
           # os.system("shutdown now -h") #shut down the Pi -h is or -r will reset
           log("cleanup made")
           killradio(p)
           log("radio killed")
           try:
              p = subprocess.Popen(["/sbin/shutdown","-h","now"])
           except:
              log(traceback.format_exc())
           log("shutdown signal emitted")
   time.sleep(0.1)
