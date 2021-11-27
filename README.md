# pi-temperature
Tools for logging and plotting Raspberry Pi CPU temperature, 
intended for use from cron.

The syslog entry has `OK` or `ALERT` according as the CPU temperature is
below or above the specified alert temperature; this allows for logcheck 
filtering and ease of grepping.

## Required JSON config file

* `alert_temp`: temperature to flag as mentioned above
* `mail_to`: list of e-mail addresses
* `mail_from`: e-mail address
* `averaging`: string used as `freq` argument of `pandas.Grouper` for 
   smoothing (averaging) the readings before plotting (can be `null`
   to ignore)
* `max_days_ago`: ignore log entries older than this (can be `null`
   to ignore)

## Original idea
```
From: dave <dave@cyw.uklinux.net>
Newsgroups: comp.sys.raspberry-pi
Subject: Re: Is sensord supposed to work on the Pi?
Message-ID: <mlc1l5$53o$1@dont-email.me>
```

```shell
if [ "$t1" -lt "$upper" -a "$t1" -gt "$lower" ]
then
  t2=`cat /sys/devices/virtual/thermal/thermal_zone0/temp`
  if [ "$t2" -lt "$upper" -a "$t2" -gt "$lower" ]
  then
   tmp=$(($t1+$t2))
   tmp=$(($tmp/2000))
   echo "t1 = $t1, t2 = $t2, temp = $tmp"
   logger -i -p info -t zone0 "zone0 temp $tmp [$t1 $t2 RAW]"
  fi
fi
```
