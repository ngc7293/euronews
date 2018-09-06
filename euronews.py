import json
import re
import requests
import signal
import sys
import subprocess

from time import sleep

# Get server URL
r = requests.get("http://www.euronews.com/api/watchlive.json")
url = "http:" + json.loads(r.text)["url"]
print("url: {}".format(url))

# Get video servers URLs
r = requests.get(url)
primary = json.loads(r.text)["primary"][:-13]
backup = json.loads(r.text)["backup"][:-13]
print("primary: {}\nbackup: {}".format(primary,backup))

# Get available streams
r = requests.get(primary + "playlist.m3u8")
stream = primary + r.text.split("\n")[2]
print("stream: {}".format(stream))

# Download
re_duration = re.compile(r'EXT-X-TARGETDURATION:(\d+)')
re_segment = re.compile(r'.*-(\d+)-(\d+)\.ts')

segments = 0
last_segment_id = 0
last_segment_timestamp = 0

out = open("euronews.ts","wb")

def sigint(sig, frame):
    print("Received SIGINT")
    out.close()

signal.signal(signal.SIGINT, sigint)

while (True):
    r = requests.get(stream)
    # Parse M3U
    lines = r.text.split("\n")
    for line in lines:
        m = re_duration.search(line)
        if m is not None:
            duration = int(m.group(1))
        
        m = re_segment.search(line)
        if m is not None:
            timestamp = int(m.group(1))
            segment = int(m.group(2))

            if (timestamp > last_segment_timestamp and segment > last_segment_id):
                print("timestamp: {}\tid: {}\tdownloading...".format(timestamp, segment), end='', flush=True)
                r = requests.get(primary + line)
                out.write(r.content)
                print("done")

                segments += 1
                last_segment_id = segment
                last_segment_timestamp = timestamp

                if (segments == 2):
                    subprocess.Popen(["mpv", "euronews.ts"])
