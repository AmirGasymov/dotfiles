#!/usr/bin/env python3
import os, sys

# gtk-layer-shell должен загружаться раньше libwayland
if "gtk-layer-shell" not in os.environ.get("LD_PRELOAD", ""):
    import ctypes.util
    _lib = ctypes.util.find_library("gtk-layer-shell")
    if _lib:
        os.environ["LD_PRELOAD"] = _lib
        os.environ["GDK_BACKEND"] = "wayland"
        os.execv(sys.executable, [sys.executable] + sys.argv)

import re, signal, subprocess, threading, traceback, warnings
warnings.filterwarnings("ignore")

LOG = "/tmp/popup.log"
def log(m):
    with open(LOG, "a") as f: f.write(m + "\n")
def _hook(t, v, tb):
    log("".join(traceback.format_exception(t, v, tb)))
sys.excepthook = _hook
open(LOG, "w").close()
log("start " + " ".join(sys.argv))

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GLib, Pango, GtkLayerShell as LS

kind = sys.argv[1]
PIDF = "/tmp/waybar-popup.pid"

# повторный запуск закрывает уже открытый попап
try:
    k, p = open(PIDF).read().split()
    if "popup.py" in open(f"/proc/{p}/cmdline").read():
        os.kill(int(p), signal.SIGTERM)
        if k == kind:
            sys.exit(0)
except Exception:
    pass
open(PIDF, "w").write(f"{kind} {os.getpid()}")
GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, Gtk.main_quit)

def run(*a):
    return subprocess.run(a, capture_output=True, text=True).stdout

def bg(fn, cb=None):
    def w():
        r = fn()
        if cb:
            GLib.idle_add(lambda: (cb(r), False)[1])
    threading.Thread(target=w, daemon=True).start()

CSS = b"""
#popupwin { background: transparent; }
#catcher { background: rgba(0,0,0,0.01); }
#card { background: rgba(30,38,24,0.97); border: 1px solid #80ad2b; border-radius: 16px; color: #e6ecd6; font-size: 16px; padding:22px ;}
scrolledwindow, viewport { background: transparent; }
.title { font-weight: bold; font-size: 19px; }
button { background: transparent; border: none; border-radius: 10px; padding: 10px 14px; color: #e6ecd6; font-size: 16px; }
button:hover { background: rgba(128,173,43,.30); }
switch { background: #3a4230; }
switch:checked { background: #80ad2b; }
entry { background: #2a3220; color: #e6ecd6; border: 1px solid #80ad2b; border-radius: 8px; padding: 6px; font-size: 16px; }
separator { background: rgba(128,173,43,.35); min-height: 1px; }
"""
prov = Gtk.CssProvider(); prov.load_from_data(CSS)
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

def make_layer(name):
    w = Gtk.Window(); w.set_name(name)
    w.set_app_paintable(True)
    vis = w.get_screen().get_rgba_visual()
    if vis: w.set_visual(vis)
    LS.init_for_window(w)
    LS.set_layer(w, LS.Layer.OVERLAY)
    return w

# невидимое окно на весь экран: клик по нему закрывает попап
catcher = make_layer("catcher")
for e in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
    LS.set_anchor(catcher, e, True)
LS.set_exclusive_zone(catcher, -1)
catcher.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
catcher.connect("button-press-event", lambda *a: Gtk.main_quit())

win = make_layer("popupwin")
LS.set_anchor(win, LS.Edge.TOP, True)
LS.set_anchor(win, LS.Edge.RIGHT, True)
LS.set_margin(win, LS.Edge.TOP, 8)
LS.set_margin(win, LS.Edge.RIGHT, 10)
LS.set_keyboard_mode(win, getattr(LS.KeyboardMode, "ON_DEMAND", LS.KeyboardMode.EXCLUSIVE))
win.connect("key-press-event", lambda w, e: Gtk.main_quit() if e.keyval == Gdk.KEY_Escape else None)

box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
box.set_name("card")
box.set_border_width(18)
box.set_size_request(400, -1)
win.add(box)

lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

def header(title, active, on_toggle):
    h = Gtk.Box(spacing=12)
    h.set_margin_top(6)
    h.set_margin_start(8)
    h.set_margin_end(8)
    l = Gtk.Label(label=title); l.set_xalign(0)
    l.get_style_context().add_class("title")
    s = Gtk.Switch(); s.set_active(active); s.set_valign(Gtk.Align.CENTER)
    s.connect("state-set", lambda sw, st: (on_toggle(st), False)[1])
    h.pack_start(l, True, True, 0); h.pack_end(s, False, False, 0)
    box.pack_start(h, False, False, 0)
    box.pack_start(Gtk.Separator(), False, False, 4)

def add_list():
    sc = Gtk.ScrolledWindow()
    sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sc.set_min_content_height(300)
    sc.set_max_content_height(520)
    sc.set_propagate_natural_height(True)
    sc.add(lst)
    box.pack_start(sc, True, True, 0)

def fill(rows):
    for c in lst.get_children(): lst.remove(c)
    for text, cb in rows:
        b = Gtk.Button(label=text)
        lbl = b.get_child()
        lbl.set_xalign(0)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        lbl.set_max_width_chars(34)
        b.connect("clicked", lambda _b, cb=cb: cb())
        lst.pack_start(b, False, False, 0)
    lst.show_all()

# ---------- WIFI ----------
def wifi_show(out):
    nets, seen = [], set()
    for line in out.splitlines():
        f = re.split(r'(?<!\\):', line)
        if len(f) < 4 or not f[1]: continue
        ssid = f[1].replace("\\:", ":")
        if ssid in seen: continue
        seen.add(ssid)
        nets.append((f[0] == "*", int(f[2] or 0), ssid, f[3] != ""))
    nets.sort(key=lambda n: (not n[0], -n[1]))
    fill([(f"{'● ' if u else '   '}{s}   {sig}%{'  🔒' if sec else ''}",
           (lambda s=s, u=u, sec=sec: wifi_click(s, u, sec))) for u, sig, s, sec in nets]
         or [("Сетей не найдено", lambda: None)])

def wifi_refresh():
    fill([("Поиск сетей…", lambda: None)])
    bg(lambda: run("nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "auto"), wifi_show)

def wifi_click(ssid, inuse, sec):
    if inuse:
        return bg(lambda: run("nmcli", "con", "down", "id", ssid), lambda _: wifi_refresh())
    saved = ssid in run("nmcli", "-t", "-f", "NAME", "con", "show").splitlines()
    if sec and not saved:
        return ask_pw(ssid)
    fill([(f"Подключение к {ssid}…", lambda: None)])
    bg(lambda: run("nmcli", "dev", "wifi", "connect", ssid), lambda _: wifi_refresh())

def ask_pw(ssid):
    for c in lst.get_children(): lst.remove(c)
    l = Gtk.Label(label=f"Пароль для {ssid}"); l.set_xalign(0)
    lst.pack_start(l, False, False, 6)
    e = Gtk.Entry(); e.set_visibility(False)
    def go(*_):
        pw = e.get_text()
        fill([(f"Подключение к {ssid}…", lambda: None)])
        bg(lambda: run("nmcli", "dev", "wifi", "connect", ssid, "password", pw), lambda _: wifi_refresh())
    e.connect("activate", go)
    lst.pack_start(e, False, False, 0)
    b = Gtk.Button(label="Подключиться"); b.connect("clicked", go)
    lst.pack_start(b, False, False, 0)
    lst.show_all(); e.grab_focus()

def wifi():
    def toggle(st):
        bg(lambda: run("nmcli", "radio", "wifi", "on" if st else "off"),
           lambda _: wifi_refresh() if st else fill([]))
    header("Wi-Fi", run("nmcli", "radio", "wifi").strip() == "enabled", toggle)
    add_list(); wifi_refresh()

# ---------- BLUETOOTH ----------
def bt_show(data):
    out, conn = data
    macs = {l.split()[1] for l in conn.splitlines() if l.startswith("Device")}
    rows = []
    for l in out.splitlines():
        p = l.split(" ", 2)
        if len(p) == 3 and p[0] == "Device":
            rows.append((f"{'● ' if p[1] in macs else '   '}{p[2]}",
                         (lambda m=p[1], c=p[1] in macs: bt_click(m, c))))
    fill(rows or [("Устройств нет — нажми Scan", lambda: None)])

def bt_refresh():
    bg(lambda: (run("bluetoothctl", "devices"), run("bluetoothctl", "devices", "Connected")), bt_show)

def bt_click(mac, connected):
    def work():
        if connected:
            run("bluetoothctl", "disconnect", mac)
        else:
            run("bluetoothctl", "pair", mac); run("bluetoothctl", "trust", mac); run("bluetoothctl", "connect", mac)
    bg(work, lambda _: bt_refresh())

def bt():
    def toggle(st):
        bg(lambda: run("bluetoothctl", "power", "on" if st else "off"), lambda _: bt_refresh())
    header("Bluetooth", "Powered: yes" in run("bluetoothctl", "show"), toggle)
    add_list(); bt_refresh()
    sb = Gtk.Button(label="Scan")
    def scan(b):
        b.set_label("Поиск…")
        bg(lambda: run("bluetoothctl", "--timeout", "8", "scan", "on"),
           lambda _: (b.set_label("Scan"), bt_refresh()))
    sb.connect("clicked", scan)
    box.pack_start(sb, False, False, 0)

# ---------- POWER ----------
def power():
    for text, cmd in [("⏻   Shutdown", ["systemctl", "poweroff"]),
                      ("↻   Reboot",   ["systemctl", "reboot"]),
                      ("⇥   Logout",   ["hyprctl", "dispatch", "exit"])]:
        b = Gtk.Button(label=text); b.get_child().set_xalign(0)
        b.connect("clicked", lambda _b, c=cmd: (subprocess.Popen(c), Gtk.main_quit()))
        box.pack_start(b, False, False, 0)

{"wifi": wifi, "bluetooth": bt, "power": power}[kind]()

catcher.show_all()
GLib.timeout_add(60, lambda: (win.show_all(), log("popup shown"), False)[2])
Gtk.main()
log("exit")