#!/bin/bash

MODE=on

if [ "x$1" = "xoff" ]; then
    MODE=off
fi

RUNDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

#config
source $RUNDIR/config.sh
DEBUG= #echo

declare -A TYPES

TYPES[intrusion]='Smart/FieldDetection/1'
TYPES[line]='Smart/LineDetection/1'
TYPES[motion]='System/Video/inputs/channels/1/motionDetection'
TYPES[pir]='WLAlarm/PIR'

SUCCESS=0
CNT=0

cd $RUNDIR

for cam in $CAMERAS; do
    for type in "${!TYPES[@]}"; do
        cmd=cameras/$cam/$type-$MODE.xml
        if [ -f $cmd ]; then
            #echo $cam-$type
            $DEBUG curl -s --digest --user $USER:$PASS -T $cmd http://$cam/ISAPI/${TYPES[$type]} > response.xml
            grep -q '<statusString>OK</statusString>' response.xml
            if [ $? -ne 0 ]; then
                SUCCESS=1
                echo Failed $cam-$type
                cat response.xml 1>&2
            else
                let CNT=$CNT+1
            fi
        fi
    done
done

rm response.xml

if [ $SUCCESS -eq 0 ]; then
    echo $MODE - $CNT - OK
else
    echo $MODE - $CNT - NOK
fi

exit $SUCCESS
