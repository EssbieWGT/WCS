#just a quick script to check out accessing og meta data 
#py ./scripts/saf.py

script_to_run = "./templates/single.py"  # Replace with the actual path
filepath = "./masterdata/saf.csv"
tsPath = "./timestamps/safTS.json"
rss_url = "https://www.google.com/alerts/feeds/07456959579114045064/2491764233870694170" #SAF
savepath = "./data/saf.csv"

import subprocess
import sys

def run_script(script_path, *args):
    """Runs a Python script using subprocess."""
    try:
        result = subprocess.run([sys.executable, script_path, *args], capture_output=True, text=True, check=True)
        print(result.stdout) # or result.stderr for error messages
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error running script: {e}")
        print(e.stderr)
        return e.returncode
    except FileNotFoundError:
        print(f"Error: Script not found at '{script_path}'")
        return 1

return_code = run_script(script_to_run, filepath, tsPath, rss_url, savepath)

if return_code == 0:
    print("Script executed successfully.")
else:
    print(f"Script execution failed with return code: {return_code}")