import os, pty, sys, select, time
# usage: ptyexec.py <input-file> -- <cmd...> ; opens cmd in a pty, waits for the container shell, sends the input file lines, then 'exit'
inp = open(sys.argv[1]).read(); cmd = sys.argv[3:]
pid, fd = pty.fork()
if pid == 0:
    os.execvp(cmd[0], cmd)
out = b""; sent = False; t0 = time.time()
def readable(timeout):
    r,_,_ = select.select([fd],[],[],timeout); return bool(r)
while time.time() - t0 < 300:
    if readable(2):
        try: data = os.read(fd, 65536)
        except OSError: break
        if not data: break
        out += data
        if not sent and (b"$ " in out[-200:] or b"# " in out[-200:] or b"Connecting" in out and b"\n" in out[-50:]):
            time.sleep(1.5)
            os.write(fd, inp.encode() + b"\n"); sent = True
            time.sleep(0.5); os.write(fd, b"exit\n")
    elif sent and time.time() - t0 > 20:
        break
try: os.waitpid(pid, 0)
except Exception: pass
sys.stdout.write(out.decode("utf-8","replace"))
