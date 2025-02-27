
#py ./scripts/gitPush.py

import subprocess
import os 

repo_path = "C:\\Users\\wesle\\Desktop\\Coding Projects\\wcs"

def git_push(message):

    try:
        subprocess.run(["git", "add",  "data/",  "timestamps/",  "web/"], check=True)
        subprocess.run(["git", "commit", "-m", "Automated Push"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True) # or "master"
        print("Git push successful!")
    except subprocess.CalledProcessError as e:
        print(f"Git push failed: {e}")

if __name__ == "__main__":
    git_push("Message")
