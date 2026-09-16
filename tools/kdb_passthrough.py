#!/usr/bin/env python3
"""kdb_passthrough.py - keep the kernel-debugger pipe open across tool runs.

THE PROBLEM.  A VirtualBox host pipe for a guest serial port accepts exactly
ONE client. The OS/2 kernel debugger talks over that port, so every tool that
wants to issue a command has to connect - and when it exits, the connection
drops. The debugger is stateful (a breakpoint list, a current context, a
half-read prompt), so reconnecting mid-session is disruptive, and two tools can
never be attached at once.

THIS IS THE FIX.  Hold ONE long-lived connection to the real host pipe open at
all times, and expose a local proxy socket that kdb_cmd.py, kdb_connect.py and
anything else can connect to and disconnect from freely, as many times as
needed, WITHOUT the underlying real connection ever dropping. Bytes are
forwarded verbatim in both directions; this adds no protocol of its own.

Run it in the background for the life of the debugging session, then point the
other tools at the proxy:

    kdb_passthrough.py &
    kdb_cmd.py --socket /tmp/dbgport_proxy r
    KDB_DBGPORT=/tmp/dbgport_proxy kdb_connect.py

One client at a time: a second connection REPLACES the first (the old one is
closed), so an abandoned tool cannot wedge the proxy. If the real pipe goes
away - the VM is powered off, say - it retries once a second until it is back,
rather than exiting and losing the session.
"""
import argparse
import os
import select
import socket
import sys
import time

DEFAULT_REAL = os.environ.get("KDB_REAL_DBGPORT", "/tmp/dbgport")
DEFAULT_PROXY = os.environ.get("KDB_PROXY_PATH", "/tmp/dbgport_proxy")


def log(msg):
    sys.stderr.write("[kdb_passthrough] %s\n" % msg)
    sys.stderr.flush()


def connect_real(path):
    """Block until the real debug pipe accepts us. Retries forever by design."""
    while True:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(path)
            s.setblocking(False)
            log("connected to real %s" % path)
            return s
        except OSError as e:
            log("connect to real failed: %s, retry in 1s" % e)
            time.sleep(1)


def serve(real_path, proxy_path):
    if os.path.exists(proxy_path):
        os.remove(proxy_path)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(proxy_path)
    listener.listen(1)
    listener.setblocking(False)
    log("listening on %s" % proxy_path)

    real = connect_real(real_path)
    client = None

    while True:
        rlist = [listener, real]
        if client is not None:
            rlist.append(client)
        try:
            readable, _, _ = select.select(rlist, [], [], 1.0)
        except OSError:
            continue

        for s in readable:
            if s is listener:
                try:
                    c, _ = listener.accept()
                    c.setblocking(False)
                    if client is not None:
                        try:
                            client.close()
                        except OSError:
                            pass
                        log("replaced existing proxy client")
                    client = c
                    log("proxy client connected")
                except OSError:
                    pass

            elif s is real:
                try:
                    data = real.recv(4096)
                    if not data:
                        raise ConnectionError("real EOF")
                    if client is not None:
                        try:
                            client.sendall(data)
                        except OSError:
                            try:
                                client.close()
                            except OSError:
                                pass
                            client = None
                            log("proxy client dropped (write failed)")
                except BlockingIOError:
                    pass
                except OSError as e:
                    log("real connection lost (%s), reconnecting" % e)
                    try:
                        real.close()
                    except OSError:
                        pass
                    real = connect_real(real_path)

            elif client is not None and s is client:
                try:
                    data = client.recv(4096)
                    if not data:
                        try:
                            client.close()
                        except OSError:
                            pass
                        client = None
                        log("proxy client disconnected")
                    else:
                        real.sendall(data)
                except BlockingIOError:
                    pass
                except OSError:
                    try:
                        client.close()
                    except OSError:
                        pass
                    client = None
                    log("proxy client dropped (read failed)")


def main():
    ap = argparse.ArgumentParser(
        prog="kdb_passthrough.py",
        description="Hold one connection to the single-client kernel-debugger "
                    "pipe open, and expose a proxy socket other tools can "
                    "attach to and drop freely.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
typical session:
  kdb_passthrough.py &                              # leave it running
  kdb_cmd.py --socket /tmp/dbgport_proxy r          # attach, run, detach
  kdb_cmd.py --socket /tmp/dbgport_proxy dp %%esp    # again, same debugger state

environment (command-line options override these):
  KDB_REAL_DBGPORT   the real VirtualBox host pipe   (default /tmp/dbgport)
  KDB_PROXY_PATH     the proxy socket to create      (default /tmp/dbgport_proxy)
  KDB_DBGPORT        read by the OTHER kdb tools - set it to the proxy path

the VM side: configure the guest serial port as a host pipe in server mode,
e.g. VBoxManage modifyvm <vm> --uart1 0x3f8 4 --uartmode1 server /tmp/dbgport.
This tool needs Unix domain sockets; for a TCP debug port, connect the tools
directly with kdb_cmd.py --socket host:port instead.

it forwards bytes unchanged and speaks no protocol of its own, so anything
that works against the real pipe works against the proxy.
""")
    ap.add_argument("--real", default=DEFAULT_REAL, metavar="PATH",
                    help="the real debug pipe to hold open "
                         "(default: %(default)s, or KDB_REAL_DBGPORT)")
    ap.add_argument("--proxy", default=DEFAULT_PROXY, metavar="PATH",
                    help="the proxy socket to create "
                         "(default: %(default)s, or KDB_PROXY_PATH)")
    args = ap.parse_args()

    if not hasattr(socket, "AF_UNIX"):
        sys.exit("this platform has no Unix domain sockets; use a TCP debug "
                 "port and connect kdb_cmd.py --socket host:port directly")
    if os.path.abspath(args.real) == os.path.abspath(args.proxy):
        sys.exit("--real and --proxy must differ (it would proxy to itself)")

    try:
        serve(args.real, args.proxy)
    except KeyboardInterrupt:
        log("stopped")


if __name__ == "__main__":
    main()
