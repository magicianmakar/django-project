#!/usr/bin/env python3
import subprocess
import sys


def is_repo_not_clean():
    output = subprocess.check_output(['git', 'status'])
    if 'nothing to commit, working tree clean' not in output.decode():
        return True

    return False


def get_excludes():
    excludes = [
        'app/wsgi.py',
        'migrations',
        'tests.py',
    ]
    return excludes


def get_tracked_files():
    tracked_files_raw = subprocess.check_output(['git', 'ls-files'])
    tracked_files = tracked_files_raw.decode().split()
    python_files = [f for f in tracked_files if f.endswith('.py')]
    return python_files


def get_effective_files(tracked_files, excludes):
    effective_files = []
    for filename in tracked_files:
        is_valid = all([key not in filename for key in excludes])
        if is_valid:
            effective_files.append(filename)

    return effective_files


def main():
    if is_repo_not_clean():
        print("Git repo is dirty; commit or stash your changes.")
        sys.exit(1)

    excludes = get_excludes()
    tracked_files = get_tracked_files()
    effective_files = get_effective_files(tracked_files, excludes)

    run_command = subprocess.run
    print("Starting ...")
    for index, path in enumerate(effective_files):
        run_command(['isort', path])
        if (index + 1) % 20 == 0:
            print(f"{index + 1} files processed.")

    print("Done.")


if __name__ == '__main__':
    main()
