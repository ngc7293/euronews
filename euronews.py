import json
import argparse
import re
import requests
import signal
import sys
import subprocess
import concurrent.futures

from time import sleep

RE_STREAM_INFO     = re.compile(r'#EXT-X-STREAM-INF:PROGRAM-ID=(?P<id>\d+),BANDWIDTH=(?P<bandwidth>\d+),RESOLUTION=(?P<width>\d+)x(?P<height>\d+)')
RE_TARGET_DURATION = re.compile(r'#EXT-X-TARGETDURATION:(?P<duration>\d+)')
RE_TS_SEGMENT      = re.compile(r'.*-(?P<timestamp>\d+)-(?P<id>\d+)\.ts')

def main(args):
    # Get server URL
    print("Requesting servers URLs")
    r = requests.get("http://www.euronews.com/api/watchlive.json")
    url = "http:" + json.loads(r.text)["url"]

    # Get video servers URLs
    r = requests.get(url)
    data = json.loads(r.text)

    if (data["status"] == "ko"):
        print("Unable to obtain servers: {}".format(data["msg"]))
        exit(1)

    primary = data["primary"][:-13]
    backup = data["backup"][:-13]

    # Get available streams
    print("Requesting available streams")
    r = requests.get(primary + "playlist.m3u8")
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
        print("Received SIGINT (threads may take some time to close...)")
        executor.shutdown(wait=False)
        out.close()
        exit(0)

    def _download_segment(url, sid):
        r = requests.get(url)
        segments[sid] = r.content
        #print("GET {}".format(sid))

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    signal.signal(signal.SIGINT, _sigint)

    out = open("euronews.ts","wb")

    segments = {}
    next_segment_id = 0

    while (True):
        # Get available segments
        r = requests.get(stream)
        lines = r.text.split("\n")

        # Extract TS file names (including timestamp and id)
        for line in lines:
            match = RE_TS_SEGMENT.match(line)
            if match is not None:
                sid = int(match.group('id'))
                #print("{}".format(sid))

                if sid > next_segment_id and sid not in segments.keys():
                    if (next_segment_id == 0):
                        next_segment_id = sid
                    segments[sid] = b''
                    executor.submit(_download_segment, primary + line, sid)

        # Write all downloaded segments to TS file
        while ((next_segment_id) in segments.keys() and segments[next_segment_id] != b''):
            out.write(segments[next_segment_id])
            #print("PUT {}".format(next_segment_id))
            del segments[next_segment_id]
            next_segment_id += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-q","--quality", type=int, help="stream quality")
    main(parser.parse_args())