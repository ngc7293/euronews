import json
import argparse
import re
import requests
from requests_futures.sessions import FuturesSession
import signal
import sys
import getpass
import subprocess
import concurrent.futures
import threading

from time import sleep

RE_STREAM_INFO     = re.compile(r'#EXT-X-STREAM-INF:PROGRAM-ID=(?P<id>\d+),BANDWIDTH=(?P<bandwidth>\d+),RESOLUTION=(?P<width>\d+)x(?P<height>\d+)')
RE_TARGET_DURATION = re.compile(r'#EXT-X-TARGETDURATION:(?P<duration>\d+)')
RE_TS_SEGMENT      = re.compile(r'.*-(?P<timestamp>\d+)-(?P<id>\d+)\.ts')

ANIM = [ '|', '/', '-', '\\' ]

def get_proxy(proxy, auth):
    if proxy is None:
        return {}

    if auth is None:
        return { 'http': proxy, 'https': proxy }

    if auth == "":
        username = input("username: ")
        password = getpass.getpass("password: ")
    else:
        authfile = open(auth, 'r')
        lines = authfile.readlines()

        if len(lines) < 2:
            print("Could not read auth file correctly")
            exit(1)

        username = lines[0].strip()
        password = lines[1].strip()

        authfile.close

    proxy = proxy[0:9] + username + ":" + password + "@" + proxy[9:]
    return { 'http': proxy, 'https': proxy }
            
    

def get_stream(quality, proxies):
    print("Requesting servers URLs")
    r = requests.get("http://www.euronews.com/api/watchlive.json", proxies=proxies)
    url = "http:" + json.loads(r.text)["url"]

    # Get video servers URLs
    r = requests.get(url, proxies=proxies)
    data = json.loads(r.text)

    if (data["status"] == "ko"):
        print("Unable to obtain servers: {}".format(data["msg"]))
        exit(1)

    primary = data["primary"][:-13] # remove trailing 'playlist.m3u8'

    # Get available streams
    print("Requesting available streams")
    r = requests.get(primary + "playlist.m3u8", proxies=proxies)
    lines = r.text.split("\n")

    streams = []
    for i in range(0, len(lines)):
        match = RE_STREAM_INFO.match(lines[i])
        if not match:
            continue

        i += 1 # Actual filename is on next line
        streams.append({"height": int(match.group("height")), "bandwidth": int(match.group("bandwidth")), "file": lines[i]})
    
    return (primary, choose_quality(streams, quality))

def choose_quality(streams, quality):
    if quality is not None:
        for stream in streams:
            if stream["height"] == quality:
                return stream["file"]
    
    print("Available streams:")
    i = 0
    for stream in streams:
        print("{}) {:4}p {:0.0f}kbps".format(i, stream["height"], stream["bandwidth"]/1000))
        i += 1

    choice = -1
    while choice < 0 or choice >= i:
        try:
            choice = int(input(">"))
        except ValueError:
            choice = -1

        if choice < 0 or choice >= i:
            print("Invalid choice")
        else:
            break

    return streams[choice]["file"]


def main(args):
    # Get server URL
    proxies = get_proxy(args.proxy, args.auth)
    (primary, stream) = get_stream(args.quality, proxies)


    # Download   
    def _sigint(sig, frame):
        nonlocal done
        print("\nReceived SIGINT (threads may take some time to close...)")
        done = True

    def _player():
        nonlocal done
        ret = subprocess.call([args.player, "euronews.ts"])
        print("\nPlayer closed with return code {}".format(ret))
        done = True

    done = False    

    session = FuturesSession(max_workers=4)
    signal.signal(signal.SIGINT, _sigint)

    out = open("euronews.ts","wb")

    segments = {}
    next_segment_id = 0
    last_segment_id = 0
    last_timestamp = 0
    total_size = 0

    anim_step = 0

    info = session.get(primary + stream, proxies=proxies)
    while not done:
        # Get available segments
        if info.done():
            lines = info.result().text.split("\n")
            # Extract TS file names (including timestamp and id)
            for line in lines:
                match = RE_TS_SEGMENT.match(line)
                if match is None:
                    continue

                timestamp = int(match.group('timestamp'))
                if timestamp > last_timestamp:
                    segments[last_segment_id] = session.get(primary + line, proxies=proxies)
                    last_timestamp = timestamp
                    last_segment_id += 1

            info = session.get(primary + stream, proxies=proxies)

        # Write all downloaded segments to TS file
        while ((next_segment_id) in segments.keys() and segments[next_segment_id].done()) and not done:
            out.write(segments[next_segment_id].result().content)
            total_size += len(segments[next_segment_id].result().content)\

            del segments[next_segment_id]
            next_segment_id += 1
            
            if (next_segment_id == 3 and args.player is not None):
                threading.Thread(target=_player).start()

        if not done:
            print("\r[SEGMENTS {:4} - BYTES {:8} - LAST TIMESTAMP {} {}]".format(next_segment_id, total_size, last_timestamp, ANIM[anim_step]), end='', flush=True)
            anim_step = (anim_step + 1) % len(ANIM)
            sleep(0.300)

    session.close()
    out.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", type=int, help="stream quality, in vertical pixels")
    parser.add_argument("--socks5",  type=str, help="socks5 proxy", dest="proxy")
    parser.add_argument("--auth", type=str, help="prompt for socks5 auth. can also point to a file with username and password on two lines", const="", nargs="?")
    parser.add_argument("--player",  type=str, help="media player to launch")
    main(parser.parse_args())