docker exec -it gkfeed-parser-redis ifconfig eth0 | grep 'inet addr' | sed -e 's/:/ /' | awk '{print $3}'
