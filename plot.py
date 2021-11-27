#!/usr/bin/env python3

from collections import defaultdict
from email.message import EmailMessage
import argparse
import bisect
import datetime
import glob
import gzip
import imghdr
import maya
import os
import platform
import re
import smtplib
import subprocess
import time

# https://matplotlib.org/gallery/text_labels_and_annotations/date.html
# https://matplotlib.org/api/_as_gen/matplotlib.pyplot.subplots.html#matplotlib.pyplot.subplots
# https://matplotlib.org/api/dates_api.html#matplotlib.dates.MonthLocator
# https://matplotlib.org/api/_as_gen/matplotlib.pyplot.plot.html#matplotlib.pyplot.plot
# https://matplotlib.org/tutorials/introductory/pyplot.html

data_files = glob.iglob('/var/log/syslog*')
FIGSIZE = (7, 3)

# Mar 12 16:30:02 honeydew zone0temp[8381]: zone0 temp OK 45.3° [raw 45277 45277]
log_pattern = re.compile(r'(.{15}).*zone0 temp.* ([\d\.]+)°')

def round_down_date(timestamp):
    d = datetime.date.fromtimestamp(timestamp)
    dt = datetime.datetime.combine(d, datetime.time(0, 0, 0))
    return int(dt.timestamp())


def read_raw_data(data_files):
    # TODO filter by identifer (col 2)
    global mail_log
    # time -> (temp, hum)
    data_to_use = dict()
    # collect all the valid data from the files
    for data_file in data_files:
        if data_file.endswith('.gz'):
            with gzip.open(data_file, 'rt', encoding='utf-8', errors='ignore') as f:
                for line in f.readlines():
                    process_line(line, data_to_use)
        else:
            with open(data_file, 'r') as f:
                for line in f.readlines():
                    process_line(line, data_to_use)
    return data_to_use


def process_line(line, data_to_use):
    global mail_log
    match = log_pattern.match(line)
    if match:
        epoch = parse_date(match.group(1))
        temp = float(match.group(2))
        if -10 < temp < 150:
            data_to_use[epoch] = temp
        else:
            mail_log.append("Rejected %s" % line)
    return


def parse_date(log_date):
    maya_date = maya.parse(log_date)
    if maya_date > maya.now():
        maya_date = maya_date.add(years=-1)
    # year is missing from syslog
    #dt = datetime.datetime.strptime('2020 ' + log_date, '%Y %b %d %H:%M:%S')
    #dt = maya_date.datetime().strftime('%Y %b %d %H:%M:%S')
    #return dt.timestamp()
    return maya_date.epoch


def reverse_days(max_days=None):
    if max_days:
        backdate = (datetime.date.today() - datetime.timedelta(days=max_days))
        return int(datetime.datetime.combine(backdate,
                                             datetime.time(0, 0, 0)).timestamp())
    return 0


def average_data(data_to_use, max_days=None, averaging=None):
    min_timestamp = reverse_days(max_days)
    raw_times = [ ts for ts in data_to_use.keys() if ts >= min_timestamp ]
    timestamps = []
    temperatures = []
    if averaging:
        time_bunches = defaultdict(list)
        temp_bunches = defaultdict(list)
        interval_starts = list(range(int(min(raw_times)), int(max(raw_times)), averaging * 60))
        for time in raw_times:
            i = bisect.bisect_right(interval_starts, time) - 1
            key = interval_starts[i]
            time_bunches[key].append(time)
            temp_bunches[key].append(data_to_use[time])
        for key in sorted(time_bunches.keys()):
            time_bunch = time_bunches[key]
            temp_bunch = temp_bunches[key]
            ave_time = int(sum(time_bunch) // len(time_bunch)) 
            timestamps.append(numpy.datetime64(ave_time, 's'))
            temperatures.append(sum(temp_bunch)/len(temp_bunch))
    else:
        raw_times.sort()
        prev_epoch = raw_times[0]
        prev_temp = data_to_use[prev_epoch]
        # Just average each pair of adjacent measurements
        for epoch in raw_times[1:]:
            ave = int((prev_epoch + epoch) // 2)
            timestamps.append(numpy.datetime64(ave, 's'))
            temp = data_to_use[epoch]
            temperatures.append((prev_temp + temp) / 2)
            prev_epoch = epoch
            prev_temp = temp
    return timestamps, temperatures


def read_and_plot(options):
    output_dir = '/tmp/zone0-plot-%i' % int(time.time())
    os.mkdir(output_dir)
    f0 = os.path.join(output_dir, 'plot.png')

    general_data = read_raw_data(data_files)

    days = dates.DayLocator(interval=1)
    days_minor = dates.HourLocator(byhour=[0,6,12,18])
    #days_format = dates.DateFormatter('%Y-%m-%d')
    days_format = dates.DateFormatter('%d')

    # smoothed plot
    all_timestamps, all_temperatures = average_data(general_data, max_days=7, averaging=options.averaging)

    fig0, ax0 = plt.subplots(figsize=FIGSIZE)
    ax0.xaxis.set_major_locator(days)
    ax0.xaxis.set_major_formatter(days_format)
    ax0.xaxis.set_minor_locator(days_minor)
    ax0.format_xdata = days_format
    ax0.grid(True, which='both')
    ax0.plot(all_timestamps, all_temperatures, 'b,-'),
    # autofmt needs to happen after data
    fig0.autofmt_xdate(rotation=60)
    plt.savefig(f0, dpi=200)
    plt.close(fig0)
    return f0


oparser = argparse.ArgumentParser(description="Plotter for CPU temperature",
                                  formatter_class=argparse.ArgumentDefaultsHelpFormatter)

oparser.add_argument("-v", dest="verbose",
                     default=False,
                     action='store_true',
                     help="verbose")

oparser.add_argument("-m", dest="mail",
                     action='append',
                     metavar='USER@EXAMPLE.COM',
                     help="send mail to this address")

oparser.add_argument("-a", dest="averaging",
                     type=int, default=None,
                     metavar='MINUTES',
                     help="average day over intervals")

oparser.add_argument("-n", dest="name",
                     type=str, default='',
                     metavar='NAME',
                     help="name for e-mail subject")

oparser.add_argument("-s", dest="sendmail",
                     default=False, action='store_true',
                     help="pipe to sendmail instead of SMTP to localhost")

options = oparser.parse_args()

import numpy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import dates

basic_message = 'Now = %s\nServer = %s' % (datetime.datetime.now().isoformat(timespec='seconds'),
                                           platform.node())
mail_log = []

f0 = read_and_plot(options)

if options.mail:
    mail = EmailMessage()
    mail.set_charset('utf-8')
    mail['To'] = ', '.join(options.mail)
    mail['From'] = options.mail[0]
    ave_str = ('%d minutes' % options.averaging) if  options.averaging else 'none'
    mail['Subject'] = 'CPU temperature %s (averaging %s)' % (options.name, ave_str)

    # https://docs.python.org/3/library/email.examples.html
    with open(f0, 'rb') as fp:
        img_data = fp.read()
    mail.add_attachment(img_data, maintype='image',
                        disposition='inline',
                        subtype=imghdr.what(None, img_data))

    mail.add_attachment('\n'.join(mail_log).encode('utf-8'),
                        disposition='inline',
                        maintype='text', subtype='plain')

    mail.add_attachment(basic_message.encode('utf-8'),
                        disposition='inline',
                        maintype='text', subtype='plain')

    if options.sendmail:
        subprocess.run(["/usr/sbin/sendmail", "-t", "-oi"], input=mail.as_string(), encoding='utf-8')
    else:
        with smtplib.SMTP('localhost') as s:
            s.send_message(mail)

else:
    for text in mail_log:
        print(text)
