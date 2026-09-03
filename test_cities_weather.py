import sys, time, json
sys.path.insert(0, 'vercel_deploy/api')
from live_info import _fetch_live_weather

for city in ['weather in banglore today', 'weather in hyderabad', 'weather in vizag', 'weather in delhi']:
    t0 = time.time()
    res = _fetch_live_weather(city)
    dt = time.time() - t0
    loc = res.get("location")
    temp = res.get("temperature_c")
    cond = res.get("condition")
    msg = f"{city} -> {loc}: {temp}C in {dt:.2f}s"
    print(msg.encode("ascii", "replace").decode())
