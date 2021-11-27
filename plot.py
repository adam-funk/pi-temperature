#!/usr/bin/env python3
import argparse
import datetime
import glob
import gzip
import imghdr
import json
import platform
import re
import subprocess
import time
from email.message import EmailMessage

import matplotlib
import maya
import numpy as np
import pandas as pd

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import dates

# https://matplotlib.org/gallery/text_labels_and_annotations/date.html
# https://matplotlib.org/api/_as_gen/matplotlib.pyplot.subplots.html#matplotlib.pyplot.subplots
# https://matplotlib.org/api/dates_api.html#matplotlib.dates.MonthLocator
# https://matplotlib.org/api/_as_gen/matplotlib.pyplot.plot.html#matplotlib.pyplot.plot
# https://matplotlib.org/tutorials/introductory/pyplot.html

data_files = glob.iglob('/var/log/syslog*')
FIG_SIZE = (7, 3)

# Mar 12 16:30:02 hostname zone0temp[8381]: zone0 temp OK 45.3° [raw 45277 45277]
log_pattern = re.compile(r'(.{15}).*zone0 temp.* ([\d.]+)°')


def meanr(x):
    # ignore NaN (blank fields in the CSV
    return round(np.nanmean(x), 1)


def medianr(x):
    # ignore NaN (blank fields in the CSV
    return round(np.nanmedian(x), 1)

def round_down_date(timestamp):
    d = datetime.date.fromtimestamp(timestamp)
    dt = datetime.datetime.combine(d, datetime.time(0, 0, 0))
    return int(dt.timestamp())


def read_raw_data(warnings):
    data_to_use = dict()
    # epoch time -> temperature (float)
    # collect all the valid data from the files
    for data_file in data_files:
        if data_file.endswith('.gz'):
            with gzip.open(data_file, 'rt', encoding='utf-8', errors='ignore') as f:
                for line in f.readlines():
                    process_line(line, data_to_use, warnings)
        else:
            with open(data_file, 'r') as f:
                for line in f.readlines():
                    process_line(line, data_to_use, warnings)
    return data_to_use


def process_line(line, data_to_use, warnings):
    match = log_pattern.match(line)
    if match:
        epoch = parse_date(match.group(1))
        temp = float(match.group(2))
        if -10 < temp < 150:
            data_to_use[epoch] = temp
        else:
            warnings.append("Rejected %s" % line)
    return


def parse_date(log_date):
    maya_date = maya.parse(log_date)
    if maya_date > maya.now():
        maya_date = maya_date.add(years=-1)
    # year is missing from syslog entries but the log entry cannot be in the future
    return maya_date.epoch


def reverse_days(max_days=None):
    if max_days:
        backdate = (datetime.date.today() - datetime.timedelta(days=max_days))
        return int(datetime.datetime.combine(backdate,
                                             datetime.time(0, 0, 0)).timestamp())
    return 0


def read_and_plot(options1, config1, warnings):
    output_file = '/tmp/zone0-plot-%i.png' % int(time.time())
    if options.verbose:
        print('output file', output_file)
    raw_data = read_raw_data(warnings)
    # raw_data is dict epoch timestamp -> temperature

    df = pd.DataFrame.from_dict(raw_data, orient='index', columns=['epoch', 'temperature'])
    df['timestamp'] = pd.to_datetime(df['epoch'], unit='s')
    df['date'] = df['timestamp'].dt.date

    if options1.verbose:
        print(df.shape)

    if config1['max_days_ago']:
        cutoff_date = datetime.date.today() - datetime.timedelta(days=config1['max_days_ago'])
        df = df[df['date'] >= cutoff_date]
        if options1.verbose:
            print(df.shape)

    if config1['averaging']:
        df = df.groupby(pd.Grouper(key='timestamp', freq=config1['averaging'])).mean()

    columns = [min, meanr, medianr, max]
    date_df = df.groupby('date').agg({'temperature': columns}).rename(
        columns={'meanr': 'mean', 'medianr': 'mdn'})

    days = dates.DayLocator(interval=1)
    days_minor = dates.HourLocator(byhour=[0, 6, 12, 18])
    days_format = dates.DateFormatter('%d')

    # smoothed plot
    all_timestamps, all_temperatures = average_data(raw_data, max_days=7, averaging=options1.averaging)

    fig0, ax0 = plt.subplots(figsize=FIG_SIZE)
    ax0.xaxis.set_major_locator(days)
    ax0.xaxis.set_major_formatter(days_format)
    ax0.xaxis.set_minor_locator(days_minor)
    ax0.format_xdata = days_format
    ax0.grid(True, which='both')
    ax0.plot(all_timestamps, all_temperatures, 'b,-'),
    # autofmt needs to happen after data
    fig0.autofmt_xdate(rotation=60)
    plt.savefig(output_file, dpi=200)
    plt.close(fig0)
    return output_file


oparser = argparse.ArgumentParser(description="Plotter for CPU temperature",
                                  formatter_class=argparse.ArgumentDefaultsHelpFormatter)

oparser.add_argument("-v", dest="verbose",
                     default=False,
                     action='store_true',
                     help="verbose")

oparser.add_argument("-c", dest="config_file",
                     required=True,
                     metavar="FILE",
                     help="JSON config file")

options = oparser.parse_args()

with open(options.config_file) as f:
    config = json.load(f)

text = [datetime.datetime.now().isoformat(timespec='seconds'), platform.node()]

figure = read_and_plot(options, config, text)

mail = EmailMessage()
mail.set_charset('utf-8')
mail['To'] = ', '.join(config['mail_to'])
mail['From'] = config['mail_from']

mail['Subject'] = 'CPU temperature %s (averaging %s)' % (platform.node(), config['averaging'])

with open(figure, 'rb') as fp:
    img_data = fp.read()

mail.add_attachment(img_data, maintype='image',
                    disposition='inline',
                    subtype=imghdr.what(None, img_data))

mail.add_attachment('\n'.join(text).encode('utf-8'),
                    disposition='inline',
                    maintype='text', subtype='plain')

subprocess.run(["/usr/sbin/sendmail", "-t", "-oi"], input=mail.as_string(), encoding='utf-8')
