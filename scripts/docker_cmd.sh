python app/main.py &
rq worker -u redis://${REDIS_HOST} &

wait -n
exit $?
