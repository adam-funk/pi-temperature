# pi-temperature
Tools for logging and plotting Raspberry Pi CPU temperature, 
intended for use from cron.

## Required JSON config file
...


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
