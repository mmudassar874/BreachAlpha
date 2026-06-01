import time, http.client, json, sys

csv_data = "company_name,breach_date,records_affected,breach_type\nEquifax,2017-09-07,147000000,data_leak\nCapital One,2019-07-29,106000000,data_leak\nMarriott,2018-11-30,500000000,data_leak\n"
boundary = "----TestBoundary123"
body = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.csv\"\r\nContent-Type: text/csv\r\n\r\n" + csv_data + "\r\n--" + boundary + "--\r\n"
headers = {"Content-Type": "multipart/form-data; boundary=" + boundary, "Content-Length": str(len(body))}

# First test simple upload
print("=== Test 1: Simple upload ===")
conn = http.client.HTTPConnection("localhost", 8000, timeout=30)
conn.request("POST", "/api/upload", body, headers)
resp = conn.getresponse()
data = json.loads(resp.read().decode())
print(f"Status: {resp.status}, Success: {data.get('success')}, Rows: {data.get('cleaned_rows')}")

# Then test analyze
print("\n=== Test 2: Upload + Analyze ===")
conn2 = http.client.HTTPConnection("localhost", 8000, timeout=120)
t = time.time()
conn2.request("POST", "/api/upload/analyze", body, headers)
resp2 = conn2.getresponse()
data2 = json.loads(resp2.read().decode())
print(f"Time: {time.time()-t:.2f}s, Status: {resp2.status}")
print(f"Total: {data2.get('total')}, Analyzed: {data2.get('analyzed')}, Failed: {data2.get('failed')}")
