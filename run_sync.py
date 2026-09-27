"""Run one incremental SkillUp market refresh from a terminal."""
import json
import os
import urllib.request

API=os.getenv("SKILLUP_API_URL","http://127.0.0.1:8000/api")
district=os.getenv("SKILLUP_DISTRICT","Pune")
req=urllib.request.Request(
    API+"/sync",
    data=json.dumps({"district":district,"max_pages":4,"lookback_days":45}).encode(),
    headers={"Content-Type":"application/json"},
    method="POST",
)
with urllib.request.urlopen(req,timeout=30) as r:
    print(r.read().decode())
