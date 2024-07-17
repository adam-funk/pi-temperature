#!/usr/bin/env python3
import argparse
import glob
import gzip
import imghdr
import json
import platform
import re
import subprocess
import warnings
from email.message import EmailMessage
from io import BytesIO
from datetime import datetime, timedelta, date, time

import matplotlib
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
LOG_PATTERN = re.compile(r'(.{15}).*zone0 temp.* ([\d.]+)°')
TIME_FORMAT='%b %w %H:%M:%S'


def meanr(x):
    # ignore NaN (blank fields in the CSV) and averages over missing times
    with warnings.catch_warnings():
        warnings.filterwarnings(action='ignore', category=RuntimeWarning, message='Mean of empty slice')
        result = round(np.nanmean(x), 1)
    return result


def medianr(x):
    # ignore NaN (blank fields in the CSV) and averages over missing times
    with warnings.catch_warnings():
        warnings.filterwarnings(action='ignore', category=RuntimeWarning, message='Mean of empty slice')
        result = round(np.nanmedian(x), 1)
    return result


def read_raw_data(warnings1, options1):
    data_to_use = dict()
    # epoch time -> temperature (float)
    # collect all the valid data from the files
    for data_file in data_files:
        if options1.verbose:
            print('Reading', data_file)
        if data_file.endswith('.gz'):
            with gzip.open(data_file, 'rt', encoding='utf-8-sig', errors='ignore') as f:
                for line in f.readlines():
                    process_line(line, data_to_use, warnings1)
        else:
            with open(data_file, 'r', encoding='utf-8-sig', errors='ignore') as f:
                for line in f.readlines():
                    process_line(line, data_to_use, warnings1)
    return data_to_use


def process_line(line, data_to_use, warnings1):
    match = LOG_PATTERN.match(line)
    if match:
        epoch = parse_date(match.group(1))
        temp = float(match.group(2))
        if -10 < temp < 150:
            data_to_use[epoch] = temp
        else:
            warnings1.append("Rejected %s" % line)
    return


def parse_date(log_date_str: str) -> int:
    log_date = datetime.strptime(log_date_str, TIME_FORMAT)
    log_date = log_date.replace(year=datetime.now().year)
    if log_date > datetime.now():
        log_date = log_date - timedelta(years=1)
    # year is missing from syslog entries but the log entry cannot be in the future
    return round(log_date.timestamp())


def reverse_days(max_days=None):
    if max_days:
        backdate = (date.today() - timedelta(days=max_days))
        return int(datetime.combine(backdate, time(0, 0, 0)).timestamp())
    return 0


def read_and_plot(options1, config1, warnings1):
    raw_data = read_raw_data(warnings1, options1)
    # raw_data is dict: epoch timestamp -> temperature

    df = pd.DataFrame.from_dict(raw_data, orient='index', columns=['temperature'])
    df['timestamp'] = pd.to_datetime(df.index, unit='s')
    df['date'] = df['timestamp'].dt.date

    if options1.verbose:
        print('full data:', df.shape)
        print(df['timestamp'].min(), df['timestamp'].min())
        print(df['date'].min(), df['date'].min())

    if config1['max_days_ago']:
        cutoff_date = date.today() - timedelta(days=config1['max_days_ago'])
        df = df[df['date'] >= cutoff_date]
        if options1.verbose:
            print('cutoff data', df.shape)

    columns = [min, meanr, medianr, max]
    dated = df.groupby('date').agg({'temperature': columns}).rename(columns={'meanr': 'mean', 'medianr': 'mdn'})
    if options1.verbose:
        print('dated data:', dated.shape)

    if config1['averaging']:
        df = df.groupby(pd.Grouper(key='timestamp', freq=config1['averaging'])).agg({'temperature': columns})
    if options1.verbose:
        print('final data:', df.shape)

    days = dates.DayLocator(interval=1)
    days_minor = dates.HourLocator(byhour=[0, 6, 12, 18])
    days_format = dates.DateFormatter('%d')

    buffer0 = BytesIO()
    fig0, ax0 = plt.subplots(figsize=FIG_SIZE)
    ax0.xaxis.set_major_locator(days)
    ax0.xaxis.set_major_formatter(days_format)
    ax0.xaxis.set_minor_locator(days_minor)
    ax0.format_xdata = days_format
    ax0.grid(True, which='major', color='gray')
    ax0.grid(True, which='minor', color='lightgray')
    ax0.plot(df.index, df['temperature'], '-')
    fig0.autofmt_xdate(rotation=60)
    plt.savefig(buffer0, dpi=200, format='png')
    plt.close(fig0)

    buffer1 = BytesIO()
    fig1, ax1 = plt.subplots(figsize=FIG_SIZE)
    ax1.xaxis.set_major_locator(days)
    ax1.xaxis.set_major_formatter(days_format)
    ax1.format_xdata = days_format
    ax1.grid(True, which='major')
    ax1.plot(dated.index, dated['temperature'], '-')
    fig1.autofmt_xdate(rotation=60)
    plt.savefig(buffer1, dpi=200, format='png')
    plt.close(fig1)

    return buffer0, buffer1, dated.to_html()


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

text = [datetime.now().isoformat(timespec='seconds'), platform.node()]

buffer_0, buffer_1, table = read_and_plot(options, config, text)

mail = EmailMessage()
mail.set_charset('utf-8')
mail['To'] = ', '.join(config['mail_to'])
mail['From'] = config['mail_from']

mail['Subject'] = 'CPU temperature %s (averaging %s)' % (platform.node(), config['averaging'])

buffer_0.seek(0)
img_data0 = buffer_0.read()

buffer_1.seek(0)
img_data1 = buffer_1.read()

mail.add_attachment(img_data0, maintype='image',
                    disposition='inline',
                    subtype=imghdr.what(None, img_data0))

mail.add_attachment(img_data1, maintype='image',
                    disposition='inline',
                    subtype=imghdr.what(None, img_data1))

mail.add_attachment(table.encode('utf-8'), disposition='inline',
                    maintype='text', subtype='html')

mail.add_attachment('\n'.join(text).encode('utf-8'),
                    disposition='inline',
                    maintype='text', subtype='plain')

subprocess.run(["/usr/sbin/sendmail", "-t", "-oi"], input=mail.as_string(), encoding='utf-8')
