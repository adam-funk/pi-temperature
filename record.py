#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import syslog
import time

source = '/sys/devices/virtual/thermal/thermal_zone0/temp'
upper = 84000
lower = 0


def get_raw_temp():
    with open(source, 'r') as f:
        stuff = f.readlines()
    t = int(''.join(stuff).strip())
    return t


oparser = argparse.ArgumentParser(description="temperature logger")

oparser.add_argument("-v", dest="verbose",
                     default=False,
                     action="store_true",
                     help="verbose output")

oparser.add_argument("-n", dest="logging",
                     default=True,
                     action="store_false",
                     help="dry run: do not write to syslog")

oparser.add_argument("-c", dest="config_file",
                     required=True,
                     metavar="FILE",
                     help="JSON config file")

options = oparser.parse_args()

with open(options.config_file) as f:
    config = json.load(f)

t0 = get_raw_temp()
time.sleep(1)
t1 = get_raw_temp()

tt = (t0 + t1) / 2000.0

summary = "OK" if tt < config['alert_temp'] else "ALERT"

message = 'zone0 temp %s %4.1f° [raw %i %i]' % (summary, tt, t0, t1)

if options.verbose:
    print(message)
if options.logging:
    syslog.openlog('zone0temp', syslog.LOG_PID)
    syslog.syslog(message)
    syslog.closelog()




