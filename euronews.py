import json
import argparse
import re
import requests
from requests_futures.sessions import FuturesSession
import signal
import sys
import subprocess
import concurrent.futures
import threading

from time import sleep

RE_STREAM_INFO     = re.compile(r'#EXT-X-STREAM-INF:PROGRAM-ID=(?P<id>\d+),BANDWIDTH=(?P<bandwidth>\d+),RESOLUTION=(?P<width>\d+)x(?P<height>\d+)')
RE_TARGET_DURATION = re.compile(r'#EXT-X-TARGETDURATION:(?P<duration>\d+)')
RE_TS_SEGMENT      = re.compile(r'.*-(?P<timestamp>\d+)-(?P<id>\d+)\.ts')

def main(args):
    # Get server URL
    proxies = {}
    if args.socks5 is not None:
        proxies = { 'http': args.socks5, 'https': args.socks5 }

    print("Requesting servers URLs")
    r = requests.get("http://www.euronews.com/api/watchlive.json", proxies=proxies)
    url = "http:" + json.loads(r.text)["url"]

    # Get video servers URLs
    r = requests.get(url, proxies=proxies)
    data = json.loads(r.text)

    if (data["status"] == "ko"):
        print("Unable to obtain servers: {}".format(data["msg"]))
        exit(1)

    primary = data["primary"][:-13]
    #backup = data["backup"][:-13] #TODO: Use backup stream if needed

    # Get available streams
    print("Requesting available streams")
    r = requests.get(primary + "playlist.m3u8", proxies=proxies)
    lines = r.text.split("\n")

    streams = {}
    for i in range(0, len(lines)):
        match = RE_STREAM_INFO.match(lines[i])
        if match:
            i += 1
            streams[int(match.group('height'))] = {"bandwidth": int(match.group("bandwidth")), "file": lines[i]}

    if (args.quality is None or args.quality not in streams):
        print("Available streams:")
        for quality in streams:
            print("{}) {:4}p {:0.0f}kbps".format(quality, quality, streams[quality]["bandwidth"]/1000))
        stream = primary + streams[int(input(">"))]["file"] #TODO: Implement input checking
    else:
        stream = primary + streams[args.quality]['file']

    # Download   
    def _sigint(sig, frame):
        nonlocal done
        print("Received SIGINT (threads may take some time to close...)")
        done = True

    def _player():
        nonlocal done
        ret = subprocess.call([args.player, "euronews.ts"])
        print("Player closed with return code {}".format(ret))
        done = True

    done = False    

    session = FuturesSession(max_workers=4)
    signal.signal(signal.SIGINT, _sigint)

    out = open("euronews.ts","wb")

    segments = {}
    next_segment_id = 0
    last_segment_id = 0
    last_timestamp = 0

    while not done:
        # Get available segments
        r = requests.get(stream, proxies=proxies)
        lines = r.text.split("\n")

        # Extract TS file names (including timestamp and id)
        for line in lines:
            match = RE_TS_SEGMENT.match(line)
            if match is not None:
                timestamp = int(match.group('timestamp'))

                if timestamp > last_timestamp:
                    segments[last_segment_id] = session.get(primary + line, proxies=proxies)
                    last_timestamp = timestamp
                    last_segment_id += 1
                    #TODO: too many indentation levels

        # Write all downloaded segments to TS file
        while ((next_segment_id) in segments.keys() and segments[next_segment_id].done()) and not done:
            out.write(segments[next_segment_id].result().content)
            del segments[next_segment_id]
            next_segment_id += 1
            if (next_segment_id == 3 and args.player is not None):
                threading.Thread(target=_player).start()

    session.close()
    out.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-q","--quality", type=int, help="stream quality, in vertical pixels")
    parser.add_argument("-s","--socks5",  type=str, help="socks5 proxy")
    parser.add_argument("-p","--player",  type=str, help="media player to launch")
    main(parser.parse_args())