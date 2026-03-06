import subprocess

def launch_process(exe_path, args):
    return subprocess.Popen([exe_path] + args)