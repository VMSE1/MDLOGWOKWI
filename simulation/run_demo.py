"""Один запуск: сервер + генератор + браузер.  python run_demo.py [сценарий] [--range-only]"""
import subprocess, sys, time, webbrowser

scn = next((a for a in sys.argv[1:] if not a.startswith("--")), "mixed")
extra = [a for a in sys.argv[1:] if a.startswith("--")]
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.app:app", "--port", "8000", "--log-level", "warning"])
time.sleep(2.5)
webbrowser.open("http://127.0.0.1:8000/")
try:
    subprocess.run([sys.executable, "-m", "sim.generator", "--scenario", scn] + extra)
except KeyboardInterrupt:
    pass
finally:
    srv.terminate()
