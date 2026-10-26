import re

with open("scratch/page_flab_1021.html", "r", encoding="utf-8") as f:
    html = f.read()

# drawChart
stream1 = re.findall(r"drawChart\(\)\s*\{.*?arrayToDataTable\(\[\s*\['min\.', 'Home', 'Away'\],(.*?)\s*\]\);", html, re.DOTALL)
print("stream1 found:", len(stream1))
if stream1:
    points = re.findall(r"\[(\d+),\s*(-?\d+),\s*(-?\d+)\]", stream1[0])
    print("stream1 points:", len(points), points[:3])

# drawChart2
stream2 = re.findall(r"drawChart2\(\)\s*\{.*?arrayToDataTable\(\[\s*\['min\.', 'Home', 'Away'\],(.*?)\s*\]\);", html, re.DOTALL)
print("stream2 found:", len(stream2))

# drawShot
shots_from = re.findall(r"fromData\s*=\s*google\.visualization\.arrayToDataTable\(\[\s*\['x', 'y'\],(.*?)\s*\]\);", html, re.DOTALL)
shots_to = re.findall(r"toData\s*=\s*google\.visualization\.arrayToDataTable\(\[\s*\['x', 'y'\],(.*?)\s*\]\);", html, re.DOTALL)
print("shots_from count:", len(shots_from), "shots_to count:", len(shots_to))
if shots_from:
    c_from = re.findall(r"\[([\d\.]+),\s*([\d\.]+)\]", shots_from[0])
    c_to = re.findall(r"\[([\d\.]+),\s*([\d\.]+)\]", shots_to[0])
    print("home shots count:", len(c_from), "sample from:", c_from[0], "to:", c_to[0])
