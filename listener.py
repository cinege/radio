#!/usr/bin/env python3
"""
Very simple HTTP server in python for logging requests
Usage::
    ./server.py [<port>]
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import logging, os, sys, time, alsaaudio, subprocess, traceback
sys.stdout = open('/home/pi/radio/listener.log', 'a')

class S(BaseHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def get_radio(self, index):
        stationcount = 6
        with open('/home/pi/radio/stations.txt', 'r') as f:
            stations = f.readlines()
            radiourl = stations[index % stationcount].replace("\n","")
        return radiourl

    def get_station(self):
        try:
           with open('/home/pi/radio/status.txt', 'r') as f:
              a = f.readlines()[0]
        except:
              a = '-1'
        return a

    def set_station(self, value):
        try:
           with open('/home/pi/radio/status.txt', 'w') as f:
              f.write(value)
        except:
           traceback.print_exc()

    def start_radio(self):
        index = self.get_station()
        m = alsaaudio.Mixer("PCM")
        try:
           url = self.get_radio(int(index))
           urlparts = url.split(",")
           m.setvolume(0)
           p = subprocess.Popen(["mplayer", urlparts[1], urlparts[2]])
           time.sleep(1.2)
           for i in range(20):
              m.setvolume(i*5)
              time.sleep(0.1)
        except:
           pass

    def kill_radio(self):
        os.system("pkill -9 mplayer")
        time.sleep(1)

    def do_GET(self):
        logging.info("GET request,\nPath: %s\nHeaders:\n%s\n", str(self.path), str(self.headers))
        self._set_response()
        self.wfile.write(bytes(self.get_station(), 'utf-8'))

    def do_POST(self):
        content_length = int(self.headers['Content-Length']) # <--- Gets the size of data
        post_data = self.rfile.read(content_length) # <--- Gets the data itself
        message = post_data.decode('utf-8')
        if message == "100":
           p = subprocess.Popen(["/sbin/shutdown","-h","now"])
        if message == "200":
           p = subprocess.Popen(["/sbin/shutdown","-r","now"])
        else:
           self.set_station(message)
           self.kill_radio()
           self.start_radio()
           logging.info("POST request,\nPath: %s\nHeaders:\n%s\n\nBody:\n%s\n",
                   str(self.path), str(self.headers), post_data.decode('utf-8'))
           self._set_response()
           self.wfile.write("POST request for {}".format(self.path).encode('utf-8'))

def run(server_class=HTTPServer, handler_class=S, port=8080):
    if not os.path.exists('/home/pi/radio/status.txt'):
       with open('/home/pi/radio/status.txt', 'w') as f:
          f.write('0')
    logging.basicConfig(level=logging.INFO)
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    logging.info('Starting httpd...\n')
    try:
       httpd.serve_forever()
    except KeyboardInterrupt:
       pass
    httpd.server_close()
    logging.info('Stopping httpd...\n')

if __name__ == '__main__':
    from sys import argv

    if len(argv) == 2:
        run(port=int(argv[1]))
    else:
        run()
