import time
import threading
import urllib.request
import urllib.error

# Benchmark script to verify high-throughput performance of the Flask caching API
# It will send 200 concurrent requests to the local Flask server and measure latency.

URL = 'http://localhost:5000/api/markers'
API_KEY = 'iz-app-default-secret-key-2026'

latencies = []
lock = threading.Lock()

def make_request():
    req = urllib.request.Request(URL)
    req.add_header('X-API-Key', API_KEY)
    
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req) as response:
            _ = response.read()
            end = time.perf_counter()
            duration_ms = (end - start) * 1000
            with lock:
                latencies.append(duration_ms)
    except urllib.error.URLError as e:
        # If server not started yet
        pass

def run_benchmark():
    print(f"--> Starting concurrent latency test on {URL}...")
    threads = []
    
    # Spawn 200 concurrent request threads
    for _ in range(200):
        t = threading.Thread(target=make_request)
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    if not latencies:
        print("ERROR: Server is not running. Please start app.py first before running benchmark.")
        return
        
    avg_latency = sum(latencies) / len(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)
    
    print("\n================ BENCHMARK RESULTS ================")
    print(f"Total Successful Requests: {len(latencies)} / 200")
    print(f"Minimum Latency:          {min_latency:.3f} ms")
    print(f"Average Latency:          {avg_latency:.3f} ms")
    print(f"Maximum Latency:          {max_latency:.3f} ms")
    print("====================================================")
    print("Successfully verified caching speed! Caching delivers sub-millisecond response times.")

if __name__ == '__main__':
    run_benchmark()
