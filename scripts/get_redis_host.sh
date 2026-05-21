docker exec -it parser-redis-1 ifconfig eth0 | grep 'inet addr' | sed -e 's/:/ /' | awk '{print $3}'
