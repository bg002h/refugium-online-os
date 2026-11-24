"""Start the graphical seat without a display manager or networked X server."""
import grp
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time

from settings import APP, BITCOIN, OPERATOR
from desktop_services import APPS, SESSION


def seat_config():
    sections = ['Section "ServerFlags"\n Option "AutoAddDevices" "false"\n Option "AllowMouseOpenFail" "true"\nEndSection',
                'Section "Device"\n Identifier "Display"\n Driver "modesetting"\n Option "AccelMethod" "none"\nEndSection',
                'Section "Screen"\n Identifier "Screen"\n Device "Display"\nEndSection']
    devices = []
    for event in sorted(Path('/sys/class/input').glob('event*')):
        name = (event/'device/name').read_text().strip().lower()
        if 'keyboard' in name or 'kbd' in name:
            role = 'CoreKeyboard'
        elif 'tablet' in name or 'mouse' in name:
            role = 'CorePointer'
        else:
            continue
        ident = event.name
        sections.append(f'Section "InputDevice"\n Identifier "{ident}"\n Driver "evdev"\n Option "Device" "/dev/input/{ident}"\nEndSection')
        devices.append(f' InputDevice "{ident}" "{role}"')
    sections.append('Section "ServerLayout"\n Identifier "Guest"\n Screen "Screen"\n'+'\n'.join(devices)+'\nEndSection')
    return '\n'.join(sections)+'\n'


def main():
    home = Path('/home')/'operator'
    home.mkdir(parents=True, exist_ok=True)
    runtime = Path('/run/desktop-user')
    for folder in (home,runtime,home/'.bitcoin',home/'.bitcoin/signet',Path('/var/lib/plocate')):
        folder.mkdir(exist_ok=True)
        os.chown(folder,OPERATOR,OPERATOR)
        os.chmod(folder,0o700)
    credentials = home/'.bitcoin/signet/.cookie'
    if not credentials.is_symlink():
        credentials.symlink_to('/run/bitcoin/.cookie')
    if not (home/'pubkeys').exists():
        shutil.copyfile(APPS/'pubkeys',home/'pubkeys')
        os.chown(home/'pubkeys',OPERATOR,OPERATOR)
    auth = Path('/run/refugium-xauthority')
    auth.touch(mode=0o600)
    subprocess.run(['xauth','-f',str(auth),'source','-'],input='add :0 . '+secrets.token_hex(16)+'\n',text=True,check=True)
    os.chown(auth,0,OPERATOR)
    os.chmod(auth,0o440)
    conf = Path('/run/refugium-xorg.conf')
    conf.write_text(seat_config())
    env = {'PATH':'/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','HOME':str(home),
           'DISPLAY':':0','XAUTHORITY':str(auth),'LANG':'C.UTF-8','XDG_RUNTIME_DIR':str(runtime),
           'XDG_SESSION_TYPE':'x11','XDG_CURRENT_DESKTOP':'Openbox','USER':'ro-operator','LOGNAME':'ro-operator',
           'LIBGL_ALWAYS_SOFTWARE':'1','SLINT_BACKEND':'winit-software','GDK_BACKEND':'x11',
           'NO_AT_BRIDGE':'1','GSETTINGS_BACKEND':'memory','PYTHONDONTWRITEBYTECODE':'1'}
    for port in Path('/sys/class/virtio-ports').glob('vport*'):
        if (port/'name').read_text().strip() == 'com.redhat.spice.0':
            device = Path('/dev')/port.name
            os.chown(device, 0, OPERATOR)
            os.chmod(device, 0o660)
            env['REFUGIUM_CLIPBOARD_PORT'] = str(device)
            break
    cache = Path('/run/desktop-pixbuf-loaders')
    with cache.open('wb') as output:
        subprocess.run(['/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders'], stdout=output, check=True)
    cache.chmod(0o644)
    env['GDK_PIXBUF_MODULE_FILE'] = str(cache)
    x = subprocess.Popen(['/usr/lib/xorg/Xorg',':0','vt1','-noreset','-nolisten','tcp','-auth',str(auth),
                          '-config',str(conf),'-logfile','/run/log/Xorg'])
    try:
        for _ in range(120):
            if x.poll() is not None:
                raise RuntimeError('X server exited')
            if Path('/tmp/.X11-unix/X0').is_socket():
                break
            time.sleep(.1)
        subprocess.run(['/usr/bin/dbus-run-session','--',str(SESSION/'session')], user=OPERATOR,group=OPERATOR,
                       extra_groups=[BITCOIN,grp.getgrnam('plocate').gr_gid],cwd=home,env=env,check=True)
    finally:
        x.terminate()
        x.wait()


if __name__=='__main__':
    main()
