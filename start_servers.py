import subprocess, time, sys

# Start backend
backend = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "breachalpha.server:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
    cwd=r"D:\New folder (2)",
    stdout=open(r"D:\New folder (2)\backend.log", "w"),
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
)
print(f"Backend started: PID {backend.pid}")

# Start frontend
frontend = subprocess.Popen(
    [r"C:\Program Files\nodejs\npm.cmd", "run", "dev"],
    cwd=r"D:\New folder (2)\frontend",
    stdout=open(r"D:\New folder (2)\frontend.log", "w"),
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
)
print(f"Frontend started: PID {frontend.pid}")

# Wait for servers to be ready
time.sleep(5)

# Check ports
import socket
for port, name in [(8000, "Backend"), (3000, "Frontend")]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("127.0.0.1", port))
    sock.close()
    status = "RUNNING" if result == 0 else "NOT READY"
    print(f"{name} (port {port}): {status}")

print("\nServers are running in the background.")
print("Frontend: http://localhost:3000")
print("Backend:  http://localhost:8000")
print("\nLogs: D:\\New folder (2)\\backend.log, D:\\New folder (2)\\frontend.log")
