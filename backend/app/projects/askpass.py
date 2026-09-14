#!/usr/bin/env python3
"""
Ephemeral GIT_ASKPASS helper for Cloud IDE.
Supplies credentials strictly to git child processes via ephemeral IPC/env.
Tokens are never written to disk, files, or git configuration.
"""
import os
import sys

def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else ""
    if "Username" in prompt:
        print("x-access-token")
    elif "Password" in prompt:
        token = os.environ.get("_CLOUDIDE_GIT_TOKEN", "")
        print(token)
    else:
        print("")

if __name__ == "__main__":
    main()
