#!/usr/bin/env python3
"""analyze.py - explore nvtrace JSONL traces.

usage: analyze.py TRACE [cmd]
  cmds:
    summary        event counts (default)
    mmaps          list all mmap events
    timeline N     print N events around each mmap on nvidia fds
    classes        histogram of RM_ALLOC hClass values
    find ADDR      events referencing an address/handle substring
    around IDX K   print K events before/after event index IDX
"""
import json
import sys
import collections


def load(path):
    return [json.loads(l) for l in open(path)]


def summary(evs):
    print(collections.Counter(e["ev"] for e in evs))
    io = collections.Counter((e.get("dev"), e.get("name", "?")) for e in evs if e["ev"] == "ioctl")
    for (dev, name), v in io.most_common():
        print(f"{v:5d} {dev or '?':12s} {name}")


def mmaps(evs):
    for i, e in enumerate(evs):
        if e["ev"] == "mmap":
            print(f"[{i}] {e['dev']:12s} fd={e['fd']:3d} addr={int(e['addr'],16):#14x} "
                  f"len={int(e['len'],16):#10x} prot={int(e['prot'],16)} off={int(e['offset'],16):#x}")


def classes(evs):
    h = collections.Counter()
    for e in evs:
        if e["ev"] == "ioctl" and "hClass" in e:
            h[e["hClass"]] += 1
    for k, v in h.most_common():
        print(f"{v:5d} hClass={k}")


def timeline(evs, n):
    idx = [i for i, e in enumerate(evs) if e["ev"] == "mmap"]
    seen = set()
    for i in idx:
        for j in range(max(0, i - n), min(len(evs), i + n + 1)):
            if j not in seen:
                seen.add(j)
                e = evs[j]
                keep = {k: v for k, v in e.items() if k not in ("pre", "post")}
                print(f"[{j}]", json.dumps(keep))
        print("---")


def find(evs, needle):
    for i, e in enumerate(evs):
        if needle.lower() in json.dumps(e).lower():
            keep = {k: v for k, v in e.items() if k not in ("pre", "post")}
            print(f"[{i}]", json.dumps(keep))


def around(evs, idx, k):
    idx = int(idx)
    k = int(k)
    for j in range(max(0, idx - k), min(len(evs), idx + k + 1)):
        e = evs[j]
        keep = {kk: vv for kk, vv in e.items() if kk not in ("pre", "post")}
        marker = ">>>" if j == idx else "   "
        print(f"{marker}[{j}]", json.dumps(keep))


if __name__ == "__main__":
    evs = load(sys.argv[1])
    cmd = sys.argv[2] if len(sys.argv) > 2 else "summary"
    if cmd == "summary":
        summary(evs)
    elif cmd == "mmaps":
        mmaps(evs)
    elif cmd == "classes":
        classes(evs)
    elif cmd == "timeline":
        timeline(evs, int(sys.argv[3]) if len(sys.argv) > 3 else 4)
    elif cmd == "find":
        find(evs, sys.argv[3])
    elif cmd == "around":
        around(evs, sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else 6)
