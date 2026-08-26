#!/bin/sh
echo "SELECT ErrNumber, Time_Start, Time_Stop, Status, Startstamp, Stopstamp, Description, Severity FROM Error_Log WHERE DAY(Startstamp) = DAY(NOW() - INTERVAL 1 DAY) AND Severity <> 0 ORDER BY Startstamp DESC" | mysql -h 172.19.46.61 -u root -prhel30 fortna | sed \
	-e s/^/\"/g \
	-e s/$/\"/g \
	-e 's/\t/\",\"/g' \
	-e s/\"\'/\"/g \
	-e s/\'\"/\"/g \
	-e 's/\"0\"$/\"INVALID\"/g' \
	-e 's/\"1\"$/\"INFORMATION ONLY\"/g' \
	-e 's/\"2\"$/\"GOOD MSG\"/g' \
	-e 's/\"3\"$/\"WARNING\"/g' \
	-e 's/\"4\"$/\"FULL WARNING\"/g' \
	-e 's/\"5\"$/\"ERROR SYSTEM STILL RUNNING\"/g' \
	-e 's/\"6\"$/\"HARD ERROR  SYSTEM STOPS\"/g' \
	-e 's/\"7\"$/\"JAM ERROR  SYSTEM STOPS\"/g' \
	-e 's/\"8\"$/\"FULLJAM\"/g' > /home/histdata/errorlog.txt
chmod 666 /home/histdata/errorlog.txt
