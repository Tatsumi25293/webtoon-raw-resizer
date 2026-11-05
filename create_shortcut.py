import os
import sys

def create_desktop_shortcut():
    desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
    target_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(target_dir, 'webtoon_resizer_qt.py')
    shortcut_path = os.path.join(desktop, 'Webtoon Raw Resizer.lnk')
    icon_path = os.path.join(target_dir, 'assets', 'icon.ico')

    python_dir = os.path.dirname(sys.executable)
    pythonw_exe = os.path.join(python_dir, 'pythonw.exe')
    if not os.path.exists(pythonw_exe):
        pythonw_exe = sys.executable

    icon_entry = f'oLink.IconLocation = "{icon_path},0"' if os.path.exists(icon_path) else ''

    vbs_code = f'''
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{pythonw_exe}"
oLink.Arguments = """{script_path}"""
oLink.WorkingDirectory = "{target_dir}"
oLink.Description = "Webtoon Raw Resizer & Enhancer"
{icon_entry}
oLink.Save
'''

    vbs_file = os.path.join(target_dir, 'make_shortcut.vbs')
    with open(vbs_file, 'w', encoding='utf-8') as f:
        f.write(vbs_code)

    os.system(f'cscript //Nologo "{vbs_file}"')
    if os.path.exists(vbs_file):
        os.remove(vbs_file)

    if os.path.exists(shortcut_path):
        print(f"[OK] Desktop shortcut created successfully at: {shortcut_path}")
    else:
        print("[!] Could not create shortcut automatically.")

if __name__ == '__main__':
    create_desktop_shortcut()
