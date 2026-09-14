#!/usr/bin/env python3
"""
Linux Command Line and Bash
===========================

A comprehensive, executable study script covering:

- Linux command-line fundamentals
- Bash concepts and shell terminology
- Navigation and paths
- File and directory operations
- File permissions and ownership
- Wildcards and expansion
- Pipes and redirection
- Search commands
- Text processing
- Processes and jobs
- System information
- Environment variables
- Archives and compression
- Networking commands
- Package management concepts
- Bash scripting fundamentals
- Functions, loops, conditions, arrays, and arguments
- Command substitution and exit status
- Safe command execution
- Debugging and shell options
- Practical command combinations
- Performance, security, and production considerations

The script is intentionally written in Python so that the educational material,
examples, and safe demonstrations can be studied from one executable file.

Some demonstrations execute read-only or low-risk Linux commands when the
script is running on Linux. Destructive commands are shown as educational
examples but are never executed automatically.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Iterable


# ============================================================================
# SECTION 1: DISPLAY HELPERS
# ============================================================================

def print_title(title: str) -> None:
    """Print a consistent section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_subtitle(title: str) -> None:
    """Print a smaller subsection heading."""
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def explain(text: str) -> None:
    """Print educational text with readable wrapping."""
    print(textwrap.fill(text.strip(), width=78))


def show_command(command: str, explanation: str | None = None) -> None:
    """Display a Bash command without executing it."""
    print(f"\n$ {command}")
    if explanation:
        print(f"  {explanation}")


def show_output(output: str) -> None:
    """Display representative command output."""
    print("  Output:")
    for line in output.strip().splitlines():
        print(f"    {line}")


def run_safe_command(
    command: list[str],
    *,
    timeout: int = 5,
    input_text: str | None = None,
) -> tuple[int, str, str]:
    """
    Run a command only when the operating system is Linux.

    This helper intentionally accepts a list rather than a shell string.
    Using shell=False avoids unnecessary shell interpretation and reduces
    command-injection risk when arguments originate from external input.
    """
    if platform.system() != "Linux":
        return (
            1,
            "",
            "This executable demonstration is available only on Linux.",
        )

    try:
        completed = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
        return completed.returncode, completed.stdout, completed.stderr
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as error:
        return 1, "", str(error)


def demonstrate(command: list[str], description: str) -> None:
    """Run a safe command and display its result."""
    print(f"\n$ {' '.join(command)}")
    print(f"  {description}")

    return_code, stdout, stderr = run_safe_command(command)

    if stdout.strip():
        show_output(stdout)

    if stderr.strip():
        print("  Error output:")
        for line in stderr.strip().splitlines():
            print(f"    {line}")

    print(f"  Exit status: {return_code}")


# ============================================================================
# SECTION 2: LINUX COMMAND-LINE FUNDAMENTALS
# ============================================================================

def fundamentals() -> None:
    print_title("1. Linux command-line fundamentals")

    explain(
        """
        A command-line interface (CLI) lets a user interact with an operating
        system by entering textual commands. A shell is the program that reads
        those commands, interprets shell syntax, expands variables and
        wildcards, launches programs, and connects commands through features
        such as pipes and redirection.

        Bash is one of the most widely used Unix shells. The command prompt is
        not itself Bash. The prompt is text displayed by the shell to indicate
        that it is ready to accept input.

        A command commonly has the structure:

            command [options] [arguments]

        For example, "ls -lah /var/log" invokes ls, supplies options -l, -a,
        and -h, and supplies /var/log as an argument.

        Linux commands are generally case-sensitive. "LS" and "ls" are
        different names. Spaces usually separate words unless quoting is used.
        """
    )

    print_subtitle("Important terminology")

    terms = {
        "Shell": "A command interpreter such as Bash.",
        "Terminal": "A program that provides a text interface to a shell.",
        "Command": "A program name or shell construct that performs an action.",
        "Option": "A modifier that changes command behavior, often beginning with '-'.",
        "Argument": "Data supplied to a command.",
        "Path": "A name identifying a file or directory.",
        "Standard input": "The default input stream, conventionally file descriptor 0.",
        "Standard output": "The default output stream, conventionally file descriptor 1.",
        "Standard error": "The diagnostic output stream, conventionally file descriptor 2.",
        "Pipe": "A mechanism connecting one command's output to another's input.",
        "Exit status": "An integer returned by a command, conventionally 0 for success.",
    }

    for name, definition in terms.items():
        print(f"{name}: {definition}")

    print_subtitle("Getting help")

    show_command("man ls", "Open the manual page for ls.")
    show_command("ls --help", "Display command-specific help when supported.")
    show_command("help cd", "Display Bash's help for the shell builtin cd.")
    show_command("type cd", "Show whether cd is a builtin, alias, function, or executable.")
    show_command("which python3", "Locate an executable found through PATH.")

    demonstrate(
        ["bash", "-c", "printf '%s\\n' \"$BASH_VERSION\""],
        "Show the Bash version when Bash is available.",
    )


# ============================================================================
# SECTION 3: NAVIGATION AND PATHS
# ============================================================================

def navigation() -> None:
    print_title("2. Navigation and paths")

    explain(
        """
        Linux uses a hierarchical filesystem. The root directory is written as
        "/". Directories branch from this root.

        An absolute path begins at "/". A relative path is interpreted from the
        current working directory.

        "." means the current directory.
        ".." means the parent directory.
        "~" normally expands to the current user's home directory.
        "-" is special to commands such as cd and refers to the previous
        directory.

        A path such as /home/user/Documents/report.txt is absolute. A path such
        as Documents/report.txt is relative.
        """
    )

    commands = [
        ("pwd", "Print the current working directory."),
        ("ls", "List directory entries."),
        ("ls -l", "Use long format."),
        ("ls -la", "Include hidden entries and use long format."),
        ("ls -lah", "Use human-readable sizes."),
        ("cd /tmp", "Change to /tmp."),
        ("cd ..", "Move to the parent directory."),
        ("cd ~", "Move to the home directory."),
        ("cd -", "Return to the previous working directory."),
    ]

    for command, description in commands:
        show_command(command, description)

    demonstrate(["pwd"], "Print the current working directory.")
    demonstrate(["bash", "-c", "printf '%s\\n' \"$HOME\""], "Print the home directory.")
    demonstrate(["ls", "-lah"], "List the current directory using a detailed format.")

    print_subtitle("Relative and absolute path examples")

    path_examples = [
        "/etc/hosts",
        "/var/log",
        "~/Documents",
        "./script.sh",
        "../backup",
        "../../project/data.csv",
    ]

    for path in path_examples:
        print(f"  {path}")

    explain(
        """
        A common mistake is assuming that every path beginning with a slash
        refers to a location relative to the current directory. It does not.
        A leading slash makes the path absolute.

        Another common mistake is forgetting spaces in filenames. A filename
        such as "annual report.txt" must be quoted or escaped when supplied to
        many shell commands.
        """
    )

    show_command('cat "annual report.txt"', "Quotes keep the filename as one argument.")
    show_command("cat annual\\ report.txt", "A backslash escapes the space.")


# ============================================================================
# SECTION 4: FILE AND DIRECTORY OPERATIONS
# ============================================================================

def file_operations() -> None:
    print_title("3. File and directory operations")

    explain(
        """
        Linux provides small commands that are designed to perform focused
        filesystem operations. Commands such as touch, mkdir, cp, mv, and rm
        are commonly combined into larger workflows.

        rm is destructive. It does not normally provide a recycle-bin-like
        recovery mechanism. Recursive deletion with rm -r is particularly
        powerful and should be used with great care.
        """
    )

    operations = [
        ("touch notes.txt", "Create an empty file or update its timestamps."),
        ("mkdir project", "Create a directory."),
        ("mkdir -p project/src/tests", "Create a directory tree if needed."),
        ("cp file.txt backup.txt", "Copy a file."),
        ("cp -r src backup", "Recursively copy a directory."),
        ("mv old.txt new.txt", "Rename or move a file."),
        ("mv report.txt reports/", "Move a file into a directory."),
        ("rm old.txt", "Remove a file."),
        ("rm -r old_directory", "Recursively remove a directory tree."),
        ("rmdir empty_directory", "Remove an empty directory."),
    ]

    for command, description in operations:
        show_command(command, description)

    print_subtitle("File inspection")

    inspection = [
        ("file document.pdf", "Identify the apparent file type."),
        ("stat document.pdf", "Display detailed filesystem metadata."),
        ("wc -l document.txt", "Count lines."),
        ("wc -w document.txt", "Count words."),
        ("wc -c document.txt", "Count bytes."),
        ("du -sh directory", "Estimate directory disk usage."),
        ("df -h", "Display filesystem disk usage."),
    ]

    for command, description in inspection:
        show_command(command, description)

    demonstrate(["bash", "-c", "printf 'Linux\\nBash\\nCLI\\n' | wc -l"], "Count lines from standard input.")

    print_subtitle("Safe deletion principle")

    explain(
        """
        Before deleting anything, verify the current directory with pwd and
        inspect the target with ls. Prefer explicit paths over ambiguous
        wildcards. Be particularly careful with commands such as rm -rf and
        never execute a destructive command simply because it appears in a
        copied command sequence.
        """
    )

    show_command("pwd")
    show_command("ls -la target/")
    show_command("rm -r target/")
    show_command("rm -rf target/", "Dangerous recursive forced deletion; shown only as an example.")


# ============================================================================
# SECTION 5: FILE CONTENT
# ============================================================================

def file_content() -> None:
    print_title("4. Reading and inspecting text files")

    explain(
        """
        Unix systems treat many resources as streams of bytes, while common
        administrative workflows operate on text. Commands such as cat, less,
        head, tail, and nl are useful for inspecting text without opening a
        graphical editor.
        """
    )

    commands = [
        ("cat file.txt", "Print the entire file."),
        ("less file.txt", "Interactively inspect a potentially large file."),
        ("head file.txt", "Show the first ten lines by default."),
        ("head -n 20 file.txt", "Show the first twenty lines."),
        ("tail file.txt", "Show the last ten lines."),
        ("tail -n 50 file.txt", "Show the last fifty lines."),
        ("tail -f application.log", "Follow appended log output."),
        ("nl -ba file.txt", "Number lines, including blank lines."),
    ]

    for command, description in commands:
        show_command(command, description)

    demonstrate(
        ["bash", "-c", "printf 'alpha\\nbeta\\ngamma\\ndelta\\n' | head -n 2"],
        "Read the first two lines of a stream.",
    )

    demonstrate(
        ["bash", "-c", "printf 'alpha\\nbeta\\ngamma\\ndelta\\n' | tail -n 2"],
        "Read the final two lines of a stream.",
    )


# ============================================================================
# SECTION 6: WILDCARDS AND EXPANSION
# ============================================================================

def expansion_and_wildcards() -> None:
    print_title("5. Wildcards, quoting, expansion, and command parsing")

    explain(
        """
        Bash performs several forms of expansion before executing a command.

        * matches zero or more characters within a pathname component.
        ? matches exactly one character within a pathname component.
        [abc] matches one character from the specified set.
        [0-9] matches one character from a range.

        Shell globbing is not the same thing as regular expressions. A common
        mistake is assuming that the syntax of grep regular expressions and
        shell pathname patterns is identical.

        Quoting controls how Bash interprets special characters.
        Single quotes preserve nearly everything literally.
        Double quotes allow parameter and command substitution but suppress
        pathname expansion and word splitting for the enclosed expansion.
        A backslash escapes the next character in contexts where it applies.
        """
    )

    patterns = [
        ("*.txt", "All .txt names in the current directory."),
        ("report?.csv", "report followed by exactly one character and .csv."),
        ("file[0-9].txt", "file followed by one digit and .txt."),
        ("[!0-9]*", "A Bash pattern beginning with a non-digit."),
    ]

    for pattern, description in patterns:
        show_command(f"ls {pattern}", description)

    print_subtitle("Quoting")

    show_command('printf "%s\\n" "$HOME"', "Double quotes preserve the expanded value as one word.")
    show_command("printf '%s\\n' '$HOME'", "Single quotes prevent variable expansion.")
    show_command("printf '%s\\n' hello\\ world", "Backslash escapes the space.")
    show_command('printf "%s\\n" "annual report.txt"', "A quoted filename containing spaces.")

    print_subtitle("Parameter expansion")

    show_command('name="Atul"; printf "%s\\n" "$name"')
    show_command('printf "%s\\n" "${name:-default}"')
    show_command('printf "%s\\n" "${name:?name is required}"')

    demonstrate(
        ["bash", "-c", 'name="Linux"; printf "Hello, %s\\n" "$name"'],
        "Demonstrate a safely quoted shell variable.",
    )


# ============================================================================
# SECTION 7: REDIRECTION AND PIPES
# ============================================================================

def redirection_and_pipes() -> None:
    print_title("6. Standard streams, redirection, and pipes")

    explain(
        """
        Every normal Unix process starts with standard input, standard output,
        and standard error. These correspond to file descriptors 0, 1, and 2.

        Redirection changes where these streams go.

        > writes standard output to a file and normally truncates it.
        >> appends standard output.
        < supplies a file as standard input.
        2> redirects standard error.
        2>> appends standard error.
        &> redirects both standard output and standard error in Bash.
        A pipe, written as |, connects standard output of one command to
        standard input of another command.

        A pipeline is powerful because each command can remain small and
        focused.
        """
    )

    examples = [
        ("printf '%s\\n' 'hello' > output.txt", "Create or replace output.txt."),
        ("printf '%s\\n' 'hello' >> output.txt", "Append to output.txt."),
        ("sort < names.txt", "Use names.txt as standard input."),
        ("command 2> errors.log", "Send diagnostics to errors.log."),
        ("command > output.log 2>&1", "Send both output streams to one file."),
        ("command1 | command2", "Connect command1 output to command2 input."),
        ("cat access.log | grep '404'", "Find HTTP 404 records in a stream."),
    ]

    for command, description in examples:
        show_command(command, description)

    demonstrate(
        ["bash", "-c", "printf 'pear\\napple\\nbanana\\n' | sort"],
        "Pipe text into sort.",
    )

    demonstrate(
        ["bash", "-c", "printf 'error\\ninfo\\nerror\\n' | grep -c error"],
        "Pipe text into grep and count matching lines.",
    )

    print_subtitle("tee")

    show_command(
        "command | tee output.txt",
        "Display pipeline output and write the same stream to a file.",
    )

    print_subtitle("Here documents and here strings")

    show_command(
        "cat <<EOF\nfirst line\nsecond line\nEOF",
        "Supply multiple lines directly to standard input.",
    )

    show_command(
        "grep 'Linux' <<< 'Linux command line'",
        "Supply one string as standard input using a Bash here string.",
    )


# ============================================================================
# SECTION 8: SEARCH COMMANDS
# ============================================================================

def search_commands() -> None:
    print_title("7. Searching for files and text")

    explain(
        """
        Linux provides several distinct search mechanisms.

        find searches filesystem objects based on properties such as name,
        type, size, timestamps, ownership, and permissions.

        grep searches text for patterns.

        locate searches a prebuilt filename database when the locate service
        and database are available.

        which, type, command -v, and whereis help identify commands and related
        files. These commands answer different questions and should not be
        treated as interchangeable.
        """
    )

    commands = [
        ("find . -name '*.py'", "Find Python files below the current directory."),
        ("find /var/log -type f -name '*.log'", "Find regular .log files."),
        ("find . -type d -name 'cache'", "Find directories named cache."),
        ("find . -type f -size +100M", "Find files larger than 100 MiB approximately."),
        ("find . -type f -mtime -1", "Find files modified within roughly the last day."),
        ("grep 'ERROR' application.log", "Find lines containing ERROR."),
        ("grep -n 'ERROR' application.log", "Include line numbers."),
        ("grep -i 'error' application.log", "Ignore case."),
        ("grep -R 'TODO' src/", "Recursively search files."),
        ("grep -E 'ERROR|WARN' application.log", "Use extended regular expressions."),
        ("grep -F '[literal]' file.txt", "Search for a literal fixed string."),
        ("command -v python3", "Find the executable Bash would resolve."),
        ("type -a python3", "Show all matching command resolutions."),
        ("whereis python3", "Locate related binary, source, or manual files."),
    ]

    for command, description in commands:
        show_command(command, description)

    demonstrate(
        ["bash", "-c", "printf 'INFO startup\\nERROR database\\nINFO ready\\n' | grep -n ERROR"],
        "Search a small stream and include line numbers.",
    )

    print_subtitle("find predicates")

    predicates = [
        "-name PATTERN",
        "-iname PATTERN",
        "-type f",
        "-type d",
        "-size +100M",
        "-mtime -7",
        "-user USER",
        "-perm MODE",
        "-empty",
    ]

    for predicate in predicates:
        print(f"  {predicate}")

    explain(
        """
        Combining find predicates can produce highly targeted searches. The
        meaning of actions such as -delete should be understood before use.
        Test a find expression without destructive actions first.
        """
    )

    show_command("find . -type f -name '*.tmp'")
    show_command("find . -type f -name '*.tmp' -print")
    show_command("find . -type f -name '*.tmp' -delete", "Destructive example; never executed by this script.")


# ============================================================================
# SECTION 9: TEXT PROCESSING
# ============================================================================

def text_processing() -> None:
    print_title("8. Text processing")

    explain(
        """
        A major Unix design principle is composing simple programs. Text
        processing commands can be chained to filter, transform, aggregate,
        and summarize streams.

        grep selects matching lines.
        cut selects fields or character ranges.
        tr translates or deletes characters.
        sort orders records.
        uniq collapses adjacent duplicate records.
        wc counts lines, words, and bytes.
        head and tail select portions of streams.
        sed performs stream editing.
        awk provides field-oriented processing and a small programming language.
        """
    )

    commands = [
        ("cut -d, -f1 data.csv", "Select the first comma-delimited field."),
        ("cut -c1-10 file.txt", "Select characters 1 through 10."),
        ("tr '[:lower:]' '[:upper:]'", "Convert lowercase characters to uppercase."),
        ("sort names.txt", "Sort lines."),
        ("sort -n numbers.txt", "Sort numerically."),
        ("sort -k2,2 data.txt", "Sort using the second field."),
        ("uniq -c", "Count adjacent identical lines."),
        ("wc -l file.txt", "Count lines."),
        ("sed 's/old/new/g' file.txt", "Replace old with new in each line of the stream."),
        ("awk '{print $1}' file.txt", "Print the first whitespace-separated field."),
        ("awk -F, '{print $1, $3}' data.csv", "Use comma as the field separator."),
    ]

    for command, description in commands:
        show_command(command, description)

    print_subtitle("Pipeline example")

    pipeline = (
        "printf 'error\\ninfo\\nerror\\nwarning\\nerror\\n' "
        "| sort | uniq -c | sort -nr"
    )
    show_command(
        pipeline,
        "Sort records, count adjacent duplicates, then sort counts numerically.",
    )

    demonstrate(
        ["bash", "-c", pipeline],
        "Execute a small text-processing pipeline.",
    )

    print_subtitle("awk example")

    awk_script = (
        "printf 'Alice,Engineering,85000\\n"
        "Bob,Sales,72000\\n"
        "Cara,Engineering,91000\\n' "
        "| awk -F, '$3 >= 80000 {print $1, $3}'"
    )

    demonstrate(
        ["bash", "-c", awk_script],
        "Select CSV-like records whose third field is at least 80000.",
    )

    print_subtitle("sed considerations")

    explain(
        """
        sed normally writes transformed text to standard output rather than
        changing the original file. In-place editing behavior varies by sed
        implementation and should be tested before using it in automation.

        A useful safety pattern is to write transformed output to a separate
        file, inspect it, and replace the original only after validation.
        """
    )


# ============================================================================
# SECTION 10: REGULAR EXPRESSIONS
# ============================================================================

def regular_expressions() -> None:
    print_title("9. Regular expressions")

    explain(
        """
        Regular expressions describe text patterns. They are different from
        shell globs.

        Common basic regular-expression constructs include:
        .       any character
        ^       beginning of line
        $       end of line
        *       zero or more repetitions of the preceding expression
        []      character class
        [^...]  negated character class

        Extended regular expressions add convenient operators such as +, ?,
        |, and grouping with parentheses. grep -E enables extended syntax.

        Regex behavior depends on the implementation and options, so scripts
        should be tested against representative input, including malformed
        and unexpected data.
        """
    )

    regex_examples = [
        ("^ERROR", "Lines beginning with ERROR."),
        ("ERROR$", "Lines ending with ERROR."),
        ("[0-9]+", "One or more digits in extended regex syntax."),
        ("^[A-Za-z_][A-Za-z0-9_]*$", "A simple identifier pattern."),
        ("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", "A basic YYYY-MM-DD shape."),
    ]

    for pattern, meaning in regex_examples:
        print(f"  {pattern:<40} {meaning}")

    demonstrate(
        ["bash", "-c", "printf 'INFO\\nERROR\\nWARNING\\n' | grep -E '^ERR'"],
        "Use an extended regular expression.",
    )


# ============================================================================
# SECTION 11: PERMISSIONS AND OWNERSHIP
# ============================================================================

def permissions() -> None:
    print_title("10. Permissions and ownership")

    explain(
        """
        Linux permissions normally distinguish three classes:

        user    the file owner
        group   members of the file's group
        other   everyone else

        Each class can have read (r), write (w), and execute (x) permission.

        For regular files:
        read    permits reading contents
        write   permits modifying contents
        execute permits executing the file as a program

        For directories:
        read    permits listing directory entries
        write   permits creating, removing, or renaming entries when other
                required permissions are also satisfied
        execute permits traversal/search through the directory

        Numeric permissions use octal values:
        r = 4
        w = 2
        x = 1

        Therefore 755 means:
        owner 7 = rwx
        group 5 = r-x
        other 5 = r-x
        """
    )

    commands = [
        ("ls -l script.sh", "Inspect permissions and ownership."),
        ("chmod u+x script.sh", "Add execute permission for the owner."),
        ("chmod 755 script.sh", "Set rwx for owner and r-x for group/others."),
        ("chmod 644 document.txt", "Set rw-r--r--."),
        ("chown user:group file", "Change ownership when authorized."),
        ("chgrp developers file", "Change group ownership when authorized."),
        ("umask", "Display the shell's file-creation permission mask."),
    ]

    for command, description in commands:
        show_command(command, description)

    print_subtitle("Permission calculation")

    modes = {
        "400": "owner read",
        "200": "owner write",
        "100": "owner execute",
        "040": "group read",
        "020": "group write",
        "010": "group execute",
        "004": "other read",
        "002": "other write",
        "001": "other execute",
    }

    for value, meaning in modes.items():
        print(f"  {value}: {meaning}")

    explain(
        """
        Avoid giving execute or write permissions more broadly than required.
        Permissions are one layer of security, not a replacement for
        authentication, application authorization, encryption, or isolation.
        """
    )


# ============================================================================
# SECTION 12: LINKS
# ============================================================================

def links() -> None:
    print_title("11. Hard links and symbolic links")

    explain(
        """
        A hard link is another directory entry referring to the same inode.
        A symbolic link is a separate filesystem object containing a path to
        another object.

        Symbolic links can cross filesystem boundaries and can point to
        directories. Hard links generally cannot cross filesystem boundaries,
        and restrictions commonly prevent hard links to directories.

        Removing a symbolic link does not remove its target. Removing one hard
        link does not necessarily remove the underlying data if other hard
        links remain.
        """
    )

    show_command("ln original.txt hardlink.txt", "Create a hard link.")
    show_command("ln -s /path/to/original.txt symlink.txt", "Create a symbolic link.")
    show_command("readlink symlink.txt", "Read the symbolic link target.")
    show_command("ls -li original.txt hardlink.txt", "Compare inode numbers.")


# ============================================================================
# SECTION 13: PROCESSES
# ============================================================================

def processes() -> None:
    print_title("12. Processes and jobs")

    explain(
        """
        A process is a running instance of a program. Linux assigns each
        process a process ID (PID). Processes have a parent-child relationship
        represented by PPID.

        ps provides process snapshots. top and similar tools provide
        continuously updated process information. kill sends a signal to a
        process; the name is historical and does not necessarily mean
        immediate termination.

        A shell can run jobs in the foreground or background. The & operator
        starts a command asynchronously from the shell's perspective.
        """
    )

    commands = [
        ("ps", "Show processes associated with the current terminal."),
        ("ps aux", "Show a broad process listing on common procps systems."),
        ("ps -ef", "Another widely used detailed process format."),
        ("top", "Interactive process and resource monitor."),
        ("pgrep -a python", "Find processes matching a name pattern."),
        ("kill PID", "Send the default TERM signal."),
        ("kill -TERM PID", "Explicitly request graceful termination."),
        ("kill -KILL PID", "Force termination; use only when necessary."),
        ("jobs", "Show shell jobs."),
        ("command &", "Run a command in the background."),
        ("fg %1", "Bring job 1 to the foreground."),
        ("bg %1", "Resume job 1 in the background."),
    ]

    for command, description in commands:
        show_command(command, description)

    demonstrate(
        ["ps", "-p", str(os.getpid()), "-o", "pid,ppid,comm"],
        "Display this Python process when running on Linux.",
    )

    print_subtitle("Signals")

    signals = [
        ("SIGTERM", "Request graceful termination."),
        ("SIGINT", "Interrupt, commonly generated by Ctrl+C."),
        ("SIGHUP", "Historically associated with terminal hangup; behavior depends on program."),
        ("SIGSTOP", "Stop a process; cannot be caught or ignored."),
        ("SIGCONT", "Continue a stopped process."),
        ("SIGKILL", "Immediately terminate; cannot be caught or handled."),
    ]

    for signal, meaning in signals:
        print(f"  {signal:<10} {meaning}")


# ============================================================================
# SECTION 14: JOB CONTROL
# ============================================================================

def job_control() -> None:
    print_title("13. Bash job control")

    explain(
        """
        Bash can manage foreground and background jobs.

        Ctrl+C normally sends SIGINT to the foreground process group.
        Ctrl+Z normally suspends the foreground job.
        bg resumes a stopped job in the background.
        fg brings a job into the foreground.
        jobs lists shell-managed jobs.

        nohup can allow a process to continue after a terminal closes, while
        disown removes a job from Bash's job table. For production services,
        a service manager such as systemd is normally more appropriate than
        manually maintained background processes.
        """
    )

    for command, description in [
        ("sleep 30", "Foreground job."),
        ("sleep 30 &", "Background job."),
        ("jobs -l", "List jobs with process IDs."),
        ("fg %1", "Bring job 1 forward."),
        ("bg %1", "Resume job 1 in the background."),
        ("nohup long_running_command &", "Detach a command from terminal hangup handling."),
        ("disown %1", "Remove a shell job from Bash's job table."),
    ]:
        show_command(command, description)


# ============================================================================
# SECTION 15: SYSTEM INFORMATION
# ============================================================================

def system_commands() -> None:
    print_title("14. System information and resource inspection")

    explain(
        """
        Linux systems expose information through commands and virtual
        filesystems such as /proc and /sys. The exact output varies by
        distribution, kernel, architecture, privileges, and installed tools.
        """
    )

    commands = [
        ("uname -a", "Display kernel and system information."),
        ("hostname", "Display the system hostname."),
        ("hostnamectl", "Inspect hostname and system metadata on systemd systems."),
        ("uptime", "Show uptime and load information."),
        ("free -h", "Display memory usage in human-readable units."),
        ("df -h", "Display filesystem capacity."),
        ("du -sh *", "Estimate sizes of entries in the current directory."),
        ("lsblk", "List block devices."),
        ("lscpu", "Display CPU information."),
        ("lsusb", "Display USB devices when available."),
        ("id", "Display user and group identity information."),
        ("whoami", "Display the effective username."),
        ("date", "Display the system date and time."),
        ("env", "Display environment variables."),
    ]

    for command, description in commands:
        show_command(command, description)

    demonstrate(["uname", "-a"], "Display kernel information.")
    demonstrate(["id"], "Display the current user's identity and groups.")
    demonstrate(["df", "-h"], "Display filesystem capacity.")


# ============================================================================
# SECTION 16: ENVIRONMENT VARIABLES
# ============================================================================

def environment_variables() -> None:
    print_title("15. Environment variables and PATH")

    explain(
        """
        Environment variables are name-value pairs inherited by child
        processes. Bash exposes shell variables and environment variables.

        PATH is a colon-separated list of directories searched for executable
        commands. When you type a command without a path, the shell can search
        PATH for a matching executable.

        Exporting a variable makes it part of the environment inherited by
        child processes.
        """
    )

    show_command('name="Linux"', "Create a shell variable.")
    show_command('export name', "Export the variable to child processes.")
    show_command('export APP_ENV=production', "Create and export an environment variable.")
    show_command('printf "%s\\n" "$PATH"', "Inspect PATH.")
    show_command('command -v python3', "See which executable Bash resolves.")

    demonstrate(
        ["bash", "-c", 'DEMO_VALUE="visible-to-child"; export DEMO_VALUE; bash -c \'printf "%s\\n" "$DEMO_VALUE"\''],
        "Demonstrate inheritance of an exported environment variable.",
    )

    print_subtitle("Variable quoting")

    show_command('value="hello world"; printf "<%s>\\n" "$value"')
    show_command('value="hello world"; printf "<%s>\\n" $value',
                 "Unquoted expansion can undergo word splitting; avoid this when one argument is intended.")


# ============================================================================
# SECTION 17: COMMAND SUBSTITUTION AND EXIT STATUS
# ============================================================================

def command_substitution_and_exit_status() -> None:
    print_title("16. Command substitution and exit status")

    explain(
        """
        Command substitution captures command output and substitutes it into
        another command. Modern Bash syntax uses $(command).

        The special parameter $? contains the exit status of the most recently
        executed command.

        By convention, status 0 means success and a nonzero value means
        failure. The precise meanings of nonzero values are program-specific.
        """
    )

    show_command('today=$(date +%F)')
    show_command('printf "Today: %s\\n" "$today"')

    demonstrate(
        ["bash", "-c", 'value=$(printf "Linux CLI"); printf "<%s>\\n" "$value"'],
        "Capture command output into a variable.",
    )

    demonstrate(
        ["bash", "-c", "true; printf 'true status=%s\\n' \"$?\"; false; printf 'false status=%s\\n' \"$?\""],
        "Observe conventional success and failure statuses.",
    )

    print_subtitle("Boolean command operators")

    show_command("command1 && command2", "Run command2 only when command1 succeeds.")
    show_command("command1 || command2", "Run command2 when command1 fails.")
    show_command("command1; command2", "Run command2 regardless of command1's status.")

    explain(
        """
        These operators are useful for control flow, but their semantics are
        based on exit status rather than on textual truth values. A command
        may return nonzero for an expected condition, so scripts should know
        the exit-status contract of commands they use.
        """
    )


# ============================================================================
# SECTION 18: SHELL SCRIPTING BASICS
# ============================================================================

def bash_scripting_basics() -> None:
    print_title("17. Bash scripting fundamentals")

    explain(
        """
        A Bash script is a text file containing shell commands and shell
        language constructs. A shebang identifies the interpreter intended to
        execute the file.

        A robust script commonly begins with a deliberate shell-option policy.
        "set -euo pipefail" is widely used, but it is not a universal safety
        guarantee. Each option has nuanced behavior and scripts must still
        handle expected failures correctly.
        """
    )

    script = r'''#!/usr/bin/env bash
set -euo pipefail

name="${1:-Guest}"

if [[ -z "$name" ]]; then
    printf 'A non-empty name is required.\n' >&2
    exit 1
fi

printf 'Hello, %s\n' "$name"
'''

    print(script)

    explain(
        """
        The example uses parameter expansion with a default, [[ ]] for a
        Bash conditional, quoted variable expansion, standard-error output,
        and an explicit exit status.
        """
    )

    print_subtitle("Shebang choices")

    show_command("#!/usr/bin/env bash", "Locate Bash through PATH.")
    show_command("#!/bin/bash", "Use a fixed Bash path when appropriate for the target system.")

    print_subtitle("Making a script executable")

    show_command("chmod +x script.sh")
    show_command("./script.sh Atul")


# ============================================================================
# SECTION 19: VARIABLES, ARRAYS, AND PARAMETERS
# ============================================================================

def variables_arrays_parameters() -> None:
    print_title("18. Bash variables, arrays, and positional parameters")

    explain(
        """
        Bash variables do not require a declaration keyword for ordinary
        assignment. There must be no spaces around the equals sign.

        Positional parameters are available as $1, $2, and so on. "$@" expands
        to the positional parameters as separate words when quoted, making it
        the preferred form for forwarding arbitrary argument lists.

        "$*" behaves differently and should not be used as a replacement for
        "$@" when preserving argument boundaries matters.
        """
    )

    examples = [
        ('name="Atul"', "Assign a string."),
        ('count=10', "Assign an integer-like string."),
        ('printf "%s\\n" "$name"', "Read a variable."),
        ('printf "script=%s\\n" "$0"', "Display script name."),
        ('printf "first=%s\\n" "$1"', "Display first argument."),
        ('printf "count=%s\\n" "$#"', "Display number of arguments."),
        ('for argument in "$@"; do printf "<%s>\\n" "$argument"; done',
         "Process each argument without losing spaces."),
    ]

    for command, description in examples:
        show_command(command, description)

    print_subtitle("Indexed arrays")

    show_command("servers=(web01 web02 db01)")
    show_command('printf "%s\\n" "${servers[0]}"')
    show_command('printf "%s\\n" "${servers[@]}"')
    show_command('printf "count=%s\\n" "${#servers[@]}"')

    print_subtitle("Associative arrays")

    show_command("declare -A ports=([http]=80 [https]=443)")
    show_command('printf "%s\\n" "${ports[https]}"')


# ============================================================================
# SECTION 20: CONDITIONS
# ============================================================================

def conditions() -> None:
    print_title("19. Conditions and test expressions")

    explain(
        """
        Bash conditionals commonly use [[ expression ]]. This is a Bash
        keyword construct rather than an external command and provides safer
        parsing behavior than many older test idioms.

        Common tests include string comparisons, integer comparisons, file
        existence tests, and permission tests.
        """
    )

    examples = [
        ('[[ -f "$file" ]]', "True when the path is a regular file."),
        ('[[ -d "$directory" ]]', "True when the path is a directory."),
        ('[[ -r "$file" ]]', "True when the file is readable."),
        ('[[ -w "$file" ]]', "True when the file is writable."),
        ('[[ -x "$file" ]]', "True when the file is executable/searchable as applicable."),
        ('[[ "$name" == "Atul" ]]', "String comparison with pattern-aware == semantics."),
        ('[[ "$count" -gt 10 ]]', "Integer greater-than comparison."),
    ]

    for expression, description in examples:
        show_command(f"if {expression}; then ...; fi", description)

    print_subtitle("if / elif / else")

    print(
        r'''if [[ "$score" -ge 90 ]]; then
    printf 'A\n'
elif [[ "$score" -ge 80 ]]; then
    printf 'B\n'
else
    printf 'Below B\n'
fi'''
    )

    print_subtitle("case")

    print(
        r'''case "$action" in
    start)
        printf 'Starting\n'
        ;;
    stop)
        printf 'Stopping\n'
        ;;
    status)
        printf 'Checking status\n'
        ;;
    *)
        printf 'Unknown action\n' >&2
        exit 2
        ;;
esac'''
    )


# ============================================================================
# SECTION 21: LOOPS AND FUNCTIONS
# ============================================================================

def loops_and_functions() -> None:
    print_title("20. Bash loops and functions")

    explain(
        """
        Loops automate repeated work. Functions group related commands and
        provide reusable interfaces. Functions return numeric status codes;
        they do not directly return arbitrary strings in the same way as a
        conventional programming-language function. Output can be captured
        using command substitution.
        """
    )

    print_subtitle("for loop")

    print(
        r'''for file in *.txt; do
    [[ -e "$file" ]] || continue
    printf 'Processing: %s\n' "$file"
done'''
    )

    print_subtitle("while loop")

    print(
        r'''while IFS= read -r line; do
    printf 'Line: %s\n' "$line"
done < input.txt'''
    )

    print_subtitle("until loop")

    print(
        r'''until command_is_successful; do
    sleep 2
done'''
    )

    print_subtitle("Function")

    print(
        r'''log_message() {
    local level="$1"
    local message="$2"

    printf '[%s] %s\n' "$level" "$message"
}

log_message INFO "Application started"'''
    )

    explain(
        """
        The local keyword keeps function variables local to the function's
        scope. Quoting "$1" and "$2" preserves argument boundaries. Functions
        should validate required arguments when they are used in production
        scripts.
        """
    )


# ============================================================================
# SECTION 22: INPUT VALIDATION
# ============================================================================

def input_validation() -> None:
    print_title("21. Input validation and safe shell usage")

    explain(
        """
        Shell scripts frequently process filenames, command-line arguments,
        environment variables, and data received from external systems.
        Untrusted input should never be treated as executable shell syntax.

        The most important habits are:

        1. Quote variable expansions.
        2. Prefer arrays over manually constructed command strings.
        3. Avoid eval.
        4. Avoid constructing shell code from user input.
        5. Validate expected formats.
        6. Use -- when supported to distinguish options from filenames.
        7. Prefer fixed command arguments over shell interpolation.
        """
    )

    print_subtitle("Unsafe pattern")

    show_command('filename="$USER_INPUT"; sh -c "cat $filename"',
                 "Unsafe when USER_INPUT is untrusted because it is interpreted as shell syntax.")

    print_subtitle("Safer pattern")

    show_command('filename="$USER_INPUT"; cat -- "$filename"',
                 "The value remains a filename argument rather than shell code.")

    print_subtitle("Arrays")

    show_command(
        'files=("report 1.txt" "report 2.txt"); rm -- "${files[@]}"',
        "Preserve filename boundaries when passing multiple arguments.",
    )

    print_subtitle("Avoid eval")

    show_command(
        'eval "$user_supplied_text"',
        "Dangerous: user input becomes shell syntax and may execute commands.",
    )

    explain(
        """
        Filenames can contain spaces, tabs, newlines, leading hyphens, and
        characters that have special meaning to the shell. Robust scripts
        should not assume that filenames are simple words.
        """
    )


# ============================================================================
# SECTION 23: XARGS
# ============================================================================

def xargs() -> None:
    print_title("22. xargs and argument construction")

    explain(
        """
        xargs converts standard input into command arguments. It is useful
        when a command needs arguments rather than standard input.

        Modern xargs can handle delimiters and parallel execution, but careless
        use can break on unusual filenames. GNU/Linux environments commonly
        support null-delimited workflows using find -print0 and xargs -0.
        """
    )

    show_command("printf '%s\\0' *.txt | xargs -0 -n 1 wc -l")
    show_command("find . -type f -print0 | xargs -0 -n 1 file")
    show_command("xargs -0 -P 4 command", "Run up to four command instances concurrently where supported.")

    explain(
        """
        Null-delimited processing is important because newline-delimited
        filename lists can be ambiguous. For example, a filename itself can
        contain a newline.
        """
    )


# ============================================================================
# SECTION 24: ARCHIVES AND COMPRESSION
# ============================================================================

def archives_and_compression() -> None:
    print_title("23. Archives and compression")

    explain(
        """
        tar primarily creates archives and extracts them. Compression is often
        combined with tar, producing formats such as .tar.gz, .tar.bz2, or
        .tar.xz.

        An archive and a compressed stream are different concepts. tar bundles
        files; gzip, bzip2, and xz compress byte streams.
        """
    )

    commands = [
        ("tar -cf archive.tar project/", "Create an uncompressed tar archive."),
        ("tar -xf archive.tar", "Extract an archive."),
        ("tar -czf archive.tar.gz project/", "Create a gzip-compressed archive."),
        ("tar -xzf archive.tar.gz", "Extract a gzip-compressed archive."),
        ("tar -cJf archive.tar.xz project/", "Create an xz-compressed archive."),
        ("tar -tf archive.tar", "List archive contents without extracting."),
        ("gzip file.log", "Compress a single file using gzip."),
        ("gunzip file.log.gz", "Decompress a gzip file."),
    ]

    for command, description in commands:
        show_command(command, description)

    explain(
        """
        Before extracting archives into a sensitive directory, inspect their
        contents. Archive extraction can be dangerous when archives contain
        unexpected absolute paths, parent-directory traversal, symlinks, or
        huge numbers of files.
        """)

    show_command("tar -tf untrusted.tar")
    show_command("tar -xf untrusted.tar")


# ============================================================================
# SECTION 25: NETWORKING
# ============================================================================

def networking() -> None:
    print_title("24. Basic networking commands")

    explain(
        """
        Linux includes command-line tools for inspecting network interfaces,
        routes, DNS behavior, connections, and HTTP resources. Exact
        availability differs by distribution.

        Modern Linux commonly uses ip rather than older tools such as ifconfig
        and route. curl is widely used for HTTP requests. ping tests network
        reachability using ICMP or related mechanisms, but failure does not
        necessarily prove that a host is completely unreachable because
        firewalls may block ICMP.
        """
    )

    commands = [
        ("ip addr", "Display network interfaces and addresses."),
        ("ip route", "Display the routing table."),
        ("ip link", "Display network links."),
        ("ss -tuln", "Display listening TCP/UDP sockets numerically."),
        ("ping -c 4 example.com", "Send four reachability probes."),
        ("curl -I https://example.com", "Request HTTP headers."),
        ("curl -sS https://example.com", "Fetch content while keeping useful errors."),
        ("dig example.com", "Query DNS when dig is installed."),
        ("resolvectl status", "Inspect resolver configuration on supported systemd setups."),
    ]

    for command, description in commands:
        show_command(command, description)

    print_subtitle("Safe HTTP inspection")

    demonstrate(
        ["curl", "-I", "--max-time", "3", "https://example.com"],
        "Make a short HTTP header request when curl and network access are available.",
    )

    explain(
        """
        Do not place passwords, API tokens, or other secrets directly in shell
        command lines. Command lines can become visible to other users through
        process inspection, shell history, logs, or monitoring systems.
        """)


# ============================================================================
# SECTION 26: PACKAGE MANAGEMENT
# ============================================================================

def package_management() -> None:
    print_title("25. Package management concepts")

    explain(
        """
        Linux distributions use package managers to install, update, remove,
        and verify software. The command depends on the distribution.

        Debian and Ubuntu commonly use apt.
        Fedora and related systems commonly use dnf.
        Arch Linux commonly uses pacman.

        Package managers resolve dependencies and obtain packages from
        configured repositories. Repository trust, package signatures, and
        update policies are important security considerations.
        """
    )

    commands = [
        ("apt update", "Refresh Debian-family package metadata."),
        ("apt upgrade", "Upgrade installed packages."),
        ("apt install PACKAGE", "Install a package."),
        ("apt remove PACKAGE", "Remove a package."),
        ("dnf check-update", "Check for available updates on DNF systems."),
        ("dnf install PACKAGE", "Install a package on DNF systems."),
        ("pacman -Syu", "Synchronize and upgrade an Arch system."),
    ]

    for command, description in commands:
        show_command(command, description)

    explain(
        """
        Package-management commands can change the entire system. Do not run
        distribution-specific commands without first identifying the
        distribution and understanding repository configuration.
        """)


# ============================================================================
# SECTION 27: SYSTEMD AND SERVICES
# ============================================================================

def services() -> None:
    print_title("26. Services and systemd")

    explain(
        """
        Many modern Linux distributions use systemd as the init system and
        service manager. systemctl controls services and units, while
        journalctl reads systemd journal records.

        Production services should generally be managed by an appropriate
        service manager rather than by a terminal session using sleep, &, or
        nohup.
        """
    )

    commands = [
        ("systemctl status nginx", "Inspect a service."),
        ("systemctl start nginx", "Start a service."),
        ("systemctl stop nginx", "Stop a service."),
        ("systemctl restart nginx", "Restart a service."),
        ("systemctl enable nginx", "Enable service startup according to systemd policy."),
        ("systemctl disable nginx", "Disable service startup."),
        ("journalctl -u nginx", "Read journal records for a service."),
        ("journalctl -u nginx -f", "Follow service logs."),
    ]

    for command, description in commands:
        show_command(command, description)


# ============================================================================
# SECTION 28: CRON AND SCHEDULING
# ============================================================================

def scheduling() -> None:
    print_title("27. Scheduling tasks")

    explain(
        """
        cron provides time-based scheduling on many Unix-like systems. A
        crontab entry has five time fields followed by a command:

        minute hour day-of-month month day-of-week command

        A scheduled script should use absolute paths where practical, define
        required environment variables explicitly, log important output, and
        handle failures. Cron's environment is usually much smaller than an
        interactive shell's environment.
        """
    )

    show_command("crontab -e", "Edit the current user's cron schedule.")
    show_command("crontab -l", "List the current user's cron entries.")

    cron_examples = [
        ("0 2 * * * /opt/scripts/backup.sh", "Run daily at 02:00."),
        ("*/15 * * * * /opt/scripts/check.sh", "Run every 15 minutes."),
        ("0 9 * * 1-5 /opt/scripts/report.sh", "Run weekdays at 09:00."),
    ]

    for expression, meaning in cron_examples:
        print(f"  {expression:<55} {meaning}")

    explain(
        """
        For complex production scheduling, dependency-aware service managers,
        orchestration systems, or dedicated schedulers may be more appropriate
        than a simple cron entry.
        """)


# ============================================================================
# SECTION 29: FILE DESCRIPTORS
# ============================================================================

def file_descriptors() -> None:
    print_title("28. File descriptors and advanced redirection")

    explain(
        """
        File descriptors are integer handles used by processes for open files
        and streams.

        0 = standard input
        1 = standard output
        2 = standard error

        Bash can create additional descriptors. This allows advanced scripts
        to keep independent input and output channels.
        """
    )

    examples = [
        ("command 1>output.log", "Redirect stdout."),
        ("command 2>error.log", "Redirect stderr."),
        ("command >all.log 2>&1", "Redirect stderr to the same destination as stdout."),
        ("command 2>&1 | grep ERROR", "Merge stderr into stdout before piping."),
        ("exec 3>audit.log", "Open descriptor 3 for output."),
        ("printf '%s\\n' message >&3", "Write through descriptor 3."),
        ("exec 3>&-", "Close descriptor 3."),
    ]

    for command, description in examples:
        show_command(command, description)

    explain(
        """
        Redirection order matters. For example, command >file 2>&1 first
        redirects stdout to file and then points stderr at the same destination.
        The reversed form command 2>&1 >file does not merge stderr into file
        in the same way.
        """)


# ============================================================================
# SECTION 30: PROCESS SUBSTITUTION
# ============================================================================

def process_substitution() -> None:
    print_title("29. Process substitution")

    explain(
        """
        Bash process substitution uses <(command) or >(command). It presents
        the output or input of a process through a path-like interface.

        It is useful when a command expects filenames but the data comes from
        another command.
        """
    )

    show_command("diff <(sort file_a.txt) <(sort file_b.txt)")
    show_command("while read -r line; do printf '%s\\n' \"$line\"; done < <(generate_data)")

    explain(
        """
        Process substitution is a Bash feature and is not portable to every
        POSIX shell. Scripts requiring strict POSIX sh compatibility should not
        assume it exists.
        """)


# ============================================================================
# SECTION 31: COMMAND GROUPING
# ============================================================================

def grouping() -> None:
    print_title("30. Command grouping and subshells")

    explain(
        """
        Parentheses create a subshell environment. Braces group commands in
        the current shell, subject to Bash syntax rules.

        Changes to shell variables made in a subshell do not normally propagate
        back to the parent shell.
        """
    )

    show_command('(cd /tmp && printf "inside=%s\\n" "$PWD"); printf "outside=%s\\n" "$PWD"')
    show_command('{ printf "first\\n"; printf "second\\n"; } > output.txt')

    explain(
        """
        Grouping is useful for controlling redirection scope. Parentheses are
        also commonly used when a group should run in a separate shell context.
        """)


# ============================================================================
# SECTION 32: SHELL OPTIONS
# ============================================================================

def shell_options() -> None:
    print_title("31. Bash shell options and debugging")

    explain(
        """
        Bash provides shell options and the set builtin for controlling
        behavior.

        -e attempts to exit when a command fails in contexts covered by Bash's
        errexit rules. Those rules have important exceptions.
        -u treats unset variables as errors in many expansion contexts.
        -o pipefail makes a pipeline's status reflect a failed component rather
        than only the final command.

        These settings improve error detection but do not eliminate the need
        for careful error handling.
        """
    )

    commands = [
        ("set -e", "Enable errexit behavior."),
        ("set -u", "Enable nounset behavior."),
        ("set -o pipefail", "Propagate pipeline failure."),
        ("set -x", "Trace expanded commands for debugging."),
        ("set +x", "Stop command tracing."),
        ("set -o", "List shell options."),
        ("bash -n script.sh", "Check syntax without executing the script."),
    ]

    for command, description in commands:
        show_command(command, description)

    print_subtitle("Tracing")

    explain(
        """
        set -x can expose expanded values. Never assume tracing is safe when
        secrets are present. Passwords, tokens, and private data can appear in
        logs or terminal output if tracing is enabled.
        """)


# ============================================================================
# SECTION 33: DEBUGGING
# ============================================================================

def debugging() -> None:
    print_title("32. Bash debugging techniques")

    explain(
        """
        Debugging shell scripts requires understanding both shell parsing and
        the behavior of external commands.

        Useful techniques include syntax checking, tracing, explicit logging,
        checking exit statuses, inspecting variables with printf, and testing
        functions independently.
        """
    )

    show_command("bash -n script.sh", "Syntax validation without execution.")
    show_command("bash -x script.sh", "Trace commands while executing.")
    show_command('printf "DEBUG: value=<%s>\\n" "$value" >&2',
                 "Write explicit diagnostics to standard error.")
    show_command("command; status=$?; printf 'status=%s\\n' \"$status\"")

    print_subtitle("Trap example")

    print(
        r'''cleanup() {
    rm -f -- "$temporary_file"
}

trap cleanup EXIT'''
    )

    explain(
        """
        Traps can perform cleanup or respond to signals. Cleanup code should
        itself be robust and should not accidentally hide the original failure.
        """)


# ============================================================================
# SECTION 34: TEMPORARY FILES
# ============================================================================

def temporary_files() -> None:
    print_title("33. Temporary files and safe temporary storage")

    explain(
        """
        Temporary data should not normally be created using predictable names
        such as /tmp/output.txt. Predictable names can create race conditions
        or allow another user or process to interfere with the file.

        mktemp is commonly used to request a unique temporary path. Scripts
        should still consider permissions, cleanup, interruption, and whether a
        temporary file is necessary at all.
        """
    )

    show_command("tmpfile=$(mktemp)")
    show_command('trap \'rm -f -- "$tmpfile"\' EXIT')
    show_command("mktemp -d", "Create a temporary directory.")

    explain(
        """
        When possible, use restrictive permissions and avoid putting secrets
        into temporary files. Remember that deleting a file does not guarantee
        secure erasure from storage media or backups.
        """)


# ============================================================================
# SECTION 35: PERFORMANCE
# ============================================================================

def performance() -> None:
    print_title("34. Performance considerations")

    explain(
        """
        Shell is excellent for orchestration and text-oriented automation, but
        it can become inefficient when performing millions of tiny operations.

        Starting an external process has overhead. Repeated commands inside a
        large loop can be significantly slower than using one process that can
        process many records.

        Pipelines are efficient for streaming data because they can process
        records incrementally rather than requiring the entire dataset in
        memory.

        Useful profiling and observation commands include time, ps, top,
        /usr/bin/time, and system monitoring tools.
        """
    )

    show_command("time ./script.sh")
    show_command("/usr/bin/time -v ./script.sh", "GNU time can provide detailed resource statistics.")
    show_command("du -sh directory")
    show_command("find . -type f | wc -l")

    explain(
        """
        Performance optimization should be evidence-driven. First identify
        whether the bottleneck is CPU, disk I/O, memory, network latency,
        process startup, filesystem metadata operations, or an external
        service.
        """)


# ============================================================================
# SECTION 36: PORTABILITY
# ============================================================================

def portability() -> None:
    print_title("35. Bash versus POSIX sh and portability")

    explain(
        """
        Bash contains features that are not guaranteed by POSIX sh.

        Examples of Bash-specific or commonly Bash-associated features include:
        arrays, [[ ]], process substitution, brace expansion, and many extended
        parameter-expansion facilities.

        A script beginning with #!/usr/bin/env bash explicitly requests Bash.
        A script intended for POSIX environments may use #!/bin/sh and must
        avoid Bash-specific syntax.

        Portability also varies among utilities. GNU coreutils, BusyBox, BSD
        utilities, and macOS utilities can have different options.
        """
    )

    print_subtitle("Comparison")

    comparison = [
        ("[[ "$name" == "$pattern" ]]", "Bash conditional", "Bash"),
        ("[ "$name" = "$value" ]", "Traditional test syntax", "POSIX-compatible"),
        ("array=(a b c)", "Indexed array", "Bash"),
        ("for x in ...", "Basic loop", "POSIX shell"),
        ("<(command)", "Process substitution", "Bash, not POSIX sh"),
    ]

    for syntax, meaning, portability_level in comparison:
        print(f"  {syntax:<32} {meaning:<28} {portability_level}")


# ============================================================================
# SECTION 37: COMMAND ALIASES AND FUNCTIONS
# ============================================================================

def aliases() -> None:
    print_title("36. Aliases and command customization")

    explain(
        """
        Aliases provide short textual substitutions in interactive Bash
        sessions. They are convenient for interactive use but are usually a
        poor interface for scripts because non-interactive shells may not load
        the same aliases.

        Functions are generally more flexible for reusable shell behavior.
        """
    )

    show_command("alias ll='ls -lah'", "Create an interactive shortcut.")
    show_command("alias", "List aliases.")
    show_command("unalias ll", "Remove an alias.")
    show_command("type ll", "Inspect how Bash resolves ll.")

    explain(
        """
        A script should call the command it requires directly instead of
        relying on a user's personal aliases.
        """)


# ============================================================================
# SECTION 38: HISTORY
# ============================================================================

def history() -> None:
    print_title("37. Bash history")

    explain(
        """
        Bash can retain commands in an interactive history. History is useful
        for repeating and reviewing commands, but it can also create a
        security concern if secrets are entered directly into commands.

        Avoid placing passwords, private keys, access tokens, and other secrets
        in command lines.
        """
    )

    show_command("history", "Display shell history.")
    show_command("history 20", "Display recent history entries.")
    show_command("!!", "Repeat the previous command in interactive Bash.")
    show_command("!grep", "Recall a previous command beginning with grep.")

    explain(
        """
        History expansion is interactive Bash behavior and should not be
        confused with command substitution or parameter expansion.
        """)


# ============================================================================
# SECTION 39: COMMON COMMAND COMBINATIONS
# ============================================================================

def practical_combinations() -> None:
    print_title("38. Practical command combinations")

    examples = [
        (
            "find . -type f -name '*.log' | wc -l",
            "Count log files.",
        ),
        (
            "grep -Rni 'error' /var/log 2>/dev/null | head",
            "Search recursively while suppressing permission diagnostics.",
        ),
        (
            "ps aux | sort -k3 -nr | head",
            "Inspect processes sorted approximately by CPU usage.",
        ),
        (
            "du -sh * 2>/dev/null | sort -h",
            "Estimate directory/file sizes and sort them naturally.",
        ),
        (
            "ip addr | grep -E 'inet '",
            "Extract IPv4 address lines from interface information.",
        ),
        (
            "journalctl -u nginx --since today | grep -i error",
            "Filter today's service journal records for errors.",
        ),
        (
            "find . -type f -print0 | xargs -0 wc -l",
            "Count lines across files while preserving unusual filenames.",
        ),
    ]

    for command, purpose in examples:
        show_command(command, purpose)

    explain(
        """
        Pipelines should be constructed around clear assumptions. For example,
        a pipeline that expects one field per line can fail when input contains
        embedded delimiters or unusual whitespace. Good shell programming
        starts with knowing the data format.
        """)


# ============================================================================
# SECTION 40: LOG PROCESSING EXAMPLE
# ============================================================================

def log_processing_example() -> None:
    print_title("39. Worked example: processing application logs")

    explain(
        """
        Consider log lines containing a timestamp, severity, and message.
        A simple pipeline can select errors, count repeated messages, and sort
        them by frequency.
        """
    )

    log_data = (
        "2026-09-14 ERROR database timeout\n"
        "2026-09-14 INFO request completed\n"
        "2026-09-14 ERROR database timeout\n"
        "2026-09-14 WARN cache miss\n"
        "2026-09-14 ERROR connection refused\n"
    )

    pipeline = (
        "grep 'ERROR' | "
        "sed 's/^[^ ]* ERROR //' | "
        "sort | uniq -c | sort -nr"
    )

    show_command(f"printf '%s' \"$LOG_DATA\" | {pipeline}")
    print("\nRepresentative input:")
    print(log_data)

    demonstrate(
        ["bash", "-c", f"printf '%s' {repr(log_data)} | {pipeline}"],
        "Select error messages, normalize the prefix, count duplicates, and rank them.",
    )


# ============================================================================
# SECTION 41: DATA PROCESSING EXAMPLE
# ============================================================================

def csv_processing_example() -> None:
    print_title("40. Worked example: CSV-like text processing")

    explain(
        """
        Shell text tools can process simple delimited data. They are useful
        when the data format is strictly controlled. They are not a complete
        CSV parser: quoted commas, embedded newlines, escaped quotes, and other
        CSV rules require a real CSV parser.
        """
    )

    csv_data = (
        "name,department,salary\n"
        "Alice,Engineering,85000\n"
        "Bob,Sales,72000\n"
        "Cara,Engineering,91000\n"
        "Dan,Finance,88000\n"
    )

    print(csv_data)

    show_command(
        "tail -n +2 employees.csv | awk -F, '$3 >= 80000 {print $1, $3}'",
        "Filter rows whose salary is at least 80000.",
    )

    demonstrate(
        [
            "bash",
            "-c",
            "printf '%s' "
            + repr(csv_data)
            + " | tail -n +2 | awk -F, '$3 >= 80000 {print $1, $3}'",
        ],
        "Process controlled comma-separated records.",
    )


# ============================================================================
# SECTION 42: BACKUP WORKFLOW
# ============================================================================

def backup_workflow() -> None:
    print_title("41. Backup workflow design")

    explain(
        """
        A basic archive workflow can combine tar, compression, timestamps,
        validation, and logging.

        A production backup process should consider retention, encryption,
        permissions, available storage, consistency of source data, failure
        detection, restore testing, and off-host copies. Creating an archive is
        not equivalent to proving that a backup strategy works.
        """
    )

    show_command(
        'backup="backup-$(date +%Y%m%d-%H%M%S).tar.gz"',
        "Construct a timestamped filename.",
    )
    show_command(
        'tar -czf "$backup" /srv/application',
        "Create a compressed archive.",
    )
    show_command(
        'tar -tzf "$backup" >/dev/null',
        "Check that the archive can be read.",
    )
    show_command(
        'sha256sum "$backup" > "$backup.sha256"',
        "Create a checksum file.",
    )

    explain(
        """
        Checksums detect accidental changes but do not themselves provide
        confidentiality, authentication, or guaranteed protection against a
        malicious actor who can modify both the archive and checksum.
        """)


# ============================================================================
# SECTION 43: SECURITY
# ============================================================================

def security() -> None:
    print_title("42. Linux command-line security")

    explain(
        """
        Shell commands have significant system privileges when run by a
        privileged account. Security therefore depends heavily on least
        privilege, careful input handling, filesystem permissions, environment
        management, and safe automation.

        Important principles include:

        - Do not run ordinary work as root unless required.
        - Use sudo for narrowly scoped privileged operations.
        - Quote variable expansions.
        - Do not use eval with untrusted data.
        - Validate filenames, identifiers, and numeric inputs.
        - Use -- before filenames where supported when a filename may begin
          with a hyphen.
        - Protect credentials from command history and process listings.
        - Use restrictive permissions for secret files.
        - Review scripts before executing them with elevated privileges.
        - Avoid blindly piping remote content into a shell.
        - Keep packages and systems updated according to an appropriate policy.
        """
    )

    security_examples = [
        ('rm -- "$filename"', "Protect against filenames beginning with '-'."),
        ('chmod 600 secret.txt', "Restrict a regular secret file to its owner."),
        ('umask 077', "Request restrictive default permissions for newly created files."),
        ('sudo command', "Perform a specific command with elevated privileges when authorized."),
    ]

    for command, explanation_text in security_examples:
        show_command(command, explanation_text)

    print_subtitle("Command injection")

    explain(
        """
        Command injection occurs when untrusted data becomes shell syntax.
        The safest design is usually to avoid a shell when a programmatic API
        can execute a fixed executable with an argument list.
        """)

    print(
        r'''Unsafe:
    sh -c "grep '$USER_PATTERN' file.txt"

Safer design:
    grep -- "$USER_PATTERN" file.txt'''
    )

    explain(
        """
        Even the safer example should be adapted when the input is intended to
        be a regular expression rather than a literal search string. The
        correct validation strategy depends on the intended data semantics.
        """)


# ============================================================================
# SECTION 44: ROOT AND SUDO
# ============================================================================

def root_and_sudo() -> None:
    print_title("43. Root, sudo, and privilege boundaries")

    explain(
        """
        The root account has extensive authority over the system. sudo allows
        authorized users to execute selected commands with elevated privileges
        according to policy.

        A secure administrative workflow minimizes the amount of code executed
        with elevated privileges. Validate inputs before crossing a privilege
        boundary and avoid running an entire interactive shell as root unless
        there is a justified operational reason.
        """
    )

    show_command("sudo -l", "Inspect commands the current user may run through sudo.")
    show_command("sudo systemctl restart nginx", "Restart one service with elevated privileges.")
    show_command("sudo -u deploy ./deploy.sh", "Run a command as a specific authorized user.")

    explain(
        """
        Never treat sudo as a substitute for understanding a command. A typo
        in a privileged command can have system-wide consequences.
        """)


# ============================================================================
# SECTION 45: SHELLCHECK-LIKE PRINCIPLES
# ============================================================================

def script_quality() -> None:
    print_title("44. Shell script quality principles")

    principles = [
        "Use a clear shebang.",
        "Quote expansions unless intentional splitting or globbing is required.",
        "Use arrays for lists of arguments.",
        "Use [[ ]] for Bash conditionals.",
        "Use local variables inside functions.",
        "Validate command-line arguments.",
        "Check important command failures.",
        "Send diagnostics to stderr.",
        "Use traps for cleanup where appropriate.",
        "Avoid eval.",
        "Avoid parsing ls output.",
        "Use find -print0 and xargs -0 for robust filename streams.",
        "Document assumptions about operating system and utility implementations.",
        "Use absolute paths in automation where PATH ambiguity is a concern.",
        "Do not expose secrets through command lines or debugging output.",
        "Test destructive operations on representative non-production data.",
    ]

    for number, principle in enumerate(principles, start=1):
        print(f"{number:2}. {principle}")

    explain(
        """
        Static analysis tools can identify many common shell mistakes, but
        static analysis is not a replacement for tests, code review, or
        understanding the environment in which the script executes.
        """)


# ============================================================================
# SECTION 46: DO NOT PARSE LS
# ============================================================================

def avoid_parsing_ls() -> None:
    print_title("45. Why parsing ls output is fragile")

    explain(
        """
        A frequent shell mistake is using ls as a machine-readable directory
        database. ls output is formatted for humans and can be affected by
        filenames containing whitespace, tabs, newlines, and unusual
        characters.

        Use shell globbing for simple controlled cases or find for structured
        filesystem traversal.
        """
    )

    show_command("for file in *; do printf '%s\\n' \"$file\"; done")
    show_command("find . -maxdepth 1 -type f -print")
    show_command("find . -maxdepth 1 -type f -print0")

    explain(
        """
        The correct approach depends on the desired behavior. The key point is
        that machine-oriented workflows should use machine-oriented output
        rather than attempting to reconstruct filenames from human-formatted
        listings.
        """)


# ============================================================================
# SECTION 47: COMMON MISTAKES
# ============================================================================

def common_mistakes() -> None:
    print_title("46. Common mistakes and why they happen")

    mistakes = [
        (
            "Using rm -rf without checking the path",
            "A destructive command can remove far more data than intended.",
        ),
        (
            "Forgetting quotes around variables",
            "Word splitting and pathname expansion can change argument boundaries.",
        ),
        (
            "Using eval on input",
            "Input can become executable shell syntax.",
        ),
        (
            "Assuming grep is a complete parser",
            "Regex matching is not equivalent to parsing structured data.",
        ),
        (
            "Parsing ls output",
            "Filenames can contain characters that make human-oriented output ambiguous.",
        ),
        (
            "Assuming Bash syntax works in /bin/sh",
            "Different shells implement different language features.",
        ),
        (
            "Ignoring exit statuses",
            "A later command may run despite an earlier failure.",
        ),
        (
            "Putting secrets in command arguments",
            "Arguments may be visible through process inspection or history.",
        ),
        (
            "Using predictable temporary filenames",
            "Race conditions and unintended file replacement can result.",
        ),
        (
            "Assuming sudo makes a script safe",
            "Privilege increases the impact of mistakes rather than eliminating them.",
        ),
        (
            "Assuming ping failure proves a server is down",
            "Network filtering can block ICMP while application traffic works.",
        ),
    ]

    for mistake, reason in mistakes:
        print(f"\n{mistake}")
        print(f"  {reason}")


# ============================================================================
# SECTION 48: LIMITATIONS AND TRADE-OFFS
# ============================================================================

def limitations_and_tradeoffs() -> None:
    print_title("47. Limitations and trade-offs")

    explain(
        """
        Shell is excellent for command orchestration, filesystem automation,
        system administration, pipelines, deployment glue, and small
        transformations. It becomes less attractive when the problem requires
        large data structures, complex error models, sophisticated concurrency,
        extensive testing frameworks, or complicated business logic.

        Python, Go, Rust, Java, and other languages may provide stronger
        abstractions for substantial applications.

        Using many small Unix commands can improve composability, but each
        process has startup and communication costs. A single larger program
        can be faster for intensive computation.

        Portability is another trade-off. Bash-specific scripts can be concise
        and expressive, while POSIX shell scripts may work across a broader
        set of Unix-like environments.
        """
    )


# ============================================================================
# SECTION 49: PRODUCTION DESIGN
# ============================================================================

def production_design() -> None:
    print_title("48. Production shell-script design")

    explain(
        """
        Production scripts should define their operating assumptions explicitly.
        Important questions include:

        - Which shell version is required?
        - Which operating systems are supported?
        - Which external commands are required?
        - Which directories and permissions are expected?
        - What happens if an intermediate command fails?
        - Can the operation safely be repeated?
        - What happens if the process is interrupted?
        - Where are logs written?
        - How are secrets supplied?
        - How is concurrency handled?
        - Can partial output be detected?
        - How is rollback performed?
        - How is success verified?

        Idempotence is particularly valuable. An idempotent operation can be
        repeated without causing unintended cumulative effects.
        """
    )

    print_subtitle("Example production structure")

    print(
        r'''#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_NAME="${0##*/}"

log() {
    printf '[%s] %s\n' "$SCRIPT_NAME" "$*" >&2
}

die() {
    log "ERROR: $*"
    exit 1
}

cleanup() {
    # Release temporary resources here.
    :
}

trap cleanup EXIT
trap 'die "Interrupted"' INT TERM

main() {
    # Validate input.
    # Prepare resources.
    # Perform the operation.
    # Validate the result.
    log "Operation completed"
}

main "$@"'''
    )


# ============================================================================
# SECTION 50: ADVANCED PIPELINE STATUS
# ============================================================================

def advanced_pipeline_status() -> None:
    print_title("49. Advanced pipeline status")

    explain(
        """
        Without pipefail, the exit status of a pipeline is normally the exit
        status of the last command. With pipefail enabled in Bash, the pipeline
        fails when a command in the pipeline fails, subject to Bash's exact
        pipeline status rules.

        PIPESTATUS is a Bash array containing the statuses of commands in the
        most recently executed foreground pipeline.
        """
    )

    show_command(
        "set -o pipefail; producer | transformer | consumer",
        "Make intermediate pipeline failures visible through the pipeline status.",
    )
    show_command(
        "printf '%s\\n' \"${PIPESTATUS[@]}\"",
        "Inspect individual pipeline statuses immediately afterward.",
    )

    demonstrate(
        [
            "bash",
            "-c",
            "false | true; printf 'without pipefail=%s\\n' \"$?\"; "
            "set -o pipefail; false | true; printf 'with pipefail=%s\\n' \"$?\"",
        ],
        "Demonstrate why pipeline status policy matters.",
    )


# ============================================================================
# SECTION 51: SIGNAL-SAFE CLEANUP
# ============================================================================

def signal_safe_cleanup() -> None:
    print_title("50. Cleanup and interruption")

    explain(
        """
        Long-running scripts can be interrupted. Temporary resources should
        ideally be cleaned up on normal completion and common termination
        signals.

        Cleanup code must be carefully designed. A trap should not blindly
        remove a path that could later refer to an unrelated file, and cleanup
        operations should be narrowly scoped.
        """
    )

    print(
        r'''tmpdir="$(mktemp -d)"

cleanup() {
    rm -rf -- "$tmpdir"
}

trap cleanup EXIT INT TERM

# Work inside "$tmpdir".'''
    )

    explain(
        """
        The example is educational. In production, the lifecycle of resources,
        permissions, ownership, and failure behavior should be reviewed before
        adopting it.
        """)


# ============================================================================
# SECTION 52: COMMAND DISCOVERY
# ============================================================================

def command_discovery() -> None:
    print_title("51. Understanding command resolution")

    explain(
        """
        When Bash receives a command name, it can resolve aliases, functions,
        builtins, and executables according to shell rules.

        command -v is a useful script-friendly way to check whether a command
        is available. type provides more detailed Bash-oriented information.
        """
    )

    show_command("type cd", "cd is normally a Bash builtin.")
    show_command("type printf", "Bash may provide printf as a builtin.")
    show_command("type ls", "Inspect how ls is resolved.")
    show_command("command -v curl", "Check whether curl is available.")
    show_command("command -v nonexistent_command", "Normally produces no successful resolution.")

    demonstrate(
        ["bash", "-c", "command -v bash"],
        "Resolve Bash using command -v.",
    )


# ============================================================================
# SECTION 53: SHELL BUILTINS VS EXTERNAL COMMANDS
# ============================================================================

def builtins_vs_external() -> None:
    print_title("52. Shell builtins versus external programs")

    explain(
        """
        Some commands are implemented inside Bash. Others are separate
        executable programs.

        cd must normally be a shell builtin because changing directory in a
        child process would not change the parent shell's working directory.

        export modifies the shell environment, so it is also implemented by the
        shell.

        Commands such as ls and grep are typically external executables,
        although exact environments can differ.
        """
    )

    for command in ["cd", "export", "printf", "read", "test", "ls", "grep"]:
        show_command(f"type {command}")


# ============================================================================
# SECTION 54: COMMAND SUBSTITUTION EDGE CASE
# ============================================================================

def command_substitution_edge_cases() -> None:
    print_title("53. Command substitution edge cases")

    explain(
        """
        Command substitution removes trailing newline characters from the
        captured output. This can matter when exact byte preservation is
        required.

        Shell variables also cannot safely represent arbitrary binary data.
        When byte-for-byte preservation is required, use appropriate file or
        binary-processing mechanisms instead of relying on shell variables.
        """
    )

    demonstrate(
        [
            "bash",
            "-c",
            "value=$(printf 'one\\ntwo\\n'); "
            "printf 'Captured value:\\n%s\\n' \"$value\"",
        ],
        "Capture multiline command output.",
    )


# ============================================================================
# SECTION 55: WORD SPLITTING
# ============================================================================

def word_splitting() -> None:
    print_title("54. Word splitting and pathname expansion")

    explain(
        """
        Unquoted parameter expansion can be subject to word splitting and
        pathname expansion. This is one of the most important sources of
        subtle shell bugs.

        If a variable contains "annual report.txt", an unquoted expansion can
        produce multiple words. If the resulting text contains wildcard
        characters, pathname expansion can further change the argument list.
        """
    )

    show_command(
        'filename="annual report.txt"; cat -- "$filename"',
        "Correct when the entire value represents one filename.",
    )

    show_command(
        'filename="annual report.txt"; cat -- $filename',
        "Potentially incorrect because the expansion is unquoted.",
    )

    demonstrate(
        ["bash", "-c", 'value="hello world"; set -- "$value"; printf "quoted argc=%s\\n" "$#"'],
        "Show one argument after quoted expansion.",
    )

    demonstrate(
        ["bash", "-c", 'value="hello world"; set -- $value; printf "unquoted argc=%s\\n" "$#"'],
        "Show how unquoted expansion can produce multiple arguments.",
    )


# ============================================================================
# SECTION 56: GLOB SAFETY
# ============================================================================

def glob_safety() -> None:
    print_title("55. Glob edge cases")

    explain(
        """
        A wildcard pattern may match nothing. Depending on shell options, Bash
        can leave the pattern unchanged or alter its behavior. nullglob causes
        unmatched patterns to expand to nothing. failglob causes an unmatched
        pattern to produce an error.

        Scripts should choose behavior deliberately when wildcard matches are
        important.
        """
    )

    show_command("shopt -s nullglob")
    show_command("shopt -s failglob")
    show_command("files=(/unlikely/path/*.missing)")

    explain(
        """
        The common guard "[[ -e "$file" ]]" can help when looping over a glob
        under default behavior, but nullglob often provides cleaner semantics
        for Bash-specific scripts.
        """)


# ============================================================================
# SECTION 57: ARITHMETIC
# ============================================================================

def arithmetic() -> None:
    print_title("56. Bash arithmetic")

    explain(
        """
        Bash supports integer arithmetic using arithmetic expansion and the
        (( )) construct. Bash arithmetic is integer-oriented; it is not a
        replacement for floating-point or arbitrary-precision numerical tools.
        """
    )

    show_command("total=$((5 + 3))")
    show_command("(( total += 10 ))")
    show_command("if (( total > 10 )); then printf 'large\\n'; fi")
    show_command("printf '%d\\n' $((2 ** 8))")

    demonstrate(
        ["bash", "-c", "a=12; b=5; printf 'sum=%d remainder=%d\\n' $((a+b)) $((a%b))"],
        "Perform integer arithmetic.",
    )

    explain(
        """
        Be careful with arithmetic expressions involving external input.
        Validate the expected numeric format before using untrusted text in
        arithmetic contexts.
        """)


# ============================================================================
# SECTION 58: READ AND IFS
# ============================================================================

def read_and_ifs() -> None:
    print_title("57. read and IFS")

    explain(
        """
        read reads data from standard input into shell variables. IFS is the
        Internal Field Separator and influences word splitting and read's
        field parsing.

        The common pattern "IFS= read -r line" reads a line without treating
        backslashes as escapes and without trimming leading/trailing whitespace
        through default IFS splitting.
        """
    )

    show_command(
        "while IFS= read -r line; do printf '%s\\n' \"$line\"; done < file.txt",
        "Robustly read a text file line by line.",
    )

    demonstrate(
        [
            "bash",
            "-c",
            "printf ' first line  \\nsecond line\\n' | "
            "while IFS= read -r line; do printf '<%s>\\n' \"$line\"; done",
        ],
        "Preserve surrounding spaces when reading lines.",
    )


# ============================================================================
# SECTION 59: NAMED PIPES
# ============================================================================

def named_pipes() -> None:
    print_title("58. Named pipes (FIFOs)")

    explain(
        """
        A named pipe is a filesystem object that provides a stream between
        processes. mkfifo creates one.

        Named pipes are useful when independently started programs need a
        streaming communication channel without creating an ordinary file for
        the data.
        """
    )

    show_command("mkfifo /tmp/myfifo")
    show_command("producer > /tmp/myfifo")
    show_command("consumer < /tmp/myfifo")
    show_command("rm /tmp/myfifo")

    explain(
        """
        Named pipes can block when one side has no reader or writer. Their
        lifecycle and permissions should be handled carefully in production.
        """)


# ============================================================================
# SECTION 60: FILESYSTEM TYPES
# ============================================================================

def filesystem_concepts() -> None:
    print_title("59. Filesystem concepts")

    explain(
        """
        Linux presents many resources through a filesystem namespace. Regular
        files, directories, symbolic links, sockets, pipes, and device nodes
        are different filesystem object types.

        Useful inspection commands include file, stat, ls -l, find -type, and
        readlink.
        """
    )

    for type_name, notation in [
        ("regular file", "-"),
        ("directory", "d"),
        ("symbolic link", "l"),
        ("socket", "s"),
        ("named pipe", "p"),
        ("character device", "c"),
        ("block device", "b"),
    ]:
        print(f"  {notation}  {type_name}")

    show_command("find . -type f")
    show_command("find . -type d")
    show_command("find . -type l")
    show_command("find . -type s")


# ============================================================================
# SECTION 61: /PROC AND /SYS
# ============================================================================

def proc_and_sys() -> None:
    print_title("60. /proc and /sys")

    explain(
        """
        /proc exposes process and kernel-related information through a
        virtual filesystem. /sys exposes kernel device and subsystem
        information through sysfs.

        These interfaces are powerful and system-dependent. Their contents
        should be treated as operating-system interfaces rather than ordinary
        persistent files.
        """
    )

    show_command("cat /proc/cpuinfo")
    show_command("cat /proc/meminfo")
    show_command("cat /proc/uptime")
    show_command("ls /proc")
    show_command("ls /sys")

    demonstrate(
        ["bash", "-c", "head -n 3 /proc/uptime"],
        "Read a small portion of /proc/uptime when available.",
    )


# ============================================================================
# SECTION 62: DISK AND STORAGE
# ============================================================================

def storage() -> None:
    print_title("61. Disk and storage inspection")

    explain(
        """
        Disk capacity and filesystem capacity are different concepts.
        df reports filesystem-level space, while du estimates the space
        consumed by files in a directory hierarchy.

        A filesystem can report low free space even when a simple directory
        listing appears small because deleted files may still be held open by
        running processes, reserved filesystem blocks may exist, or storage
        can be consumed outside the inspected directory.
        """
    )

    commands = [
        ("df -h", "Filesystem capacity."),
        ("df -i", "Filesystem inode usage."),
        ("du -sh /var/*", "Estimate sizes under /var."),
        ("lsblk -f", "Inspect block devices and filesystem information."),
        ("find /var -type f -size +1G", "Find large files when permitted."),
    ]

    for command, description in commands:
        show_command(command, description)


# ============================================================================
# SECTION 63: ENVIRONMENT SECURITY
# ============================================================================

def environment_security() -> None:
    print_title("62. Environment-variable security")

    explain(
        """
        Environment variables are convenient for configuration, but they are
        not automatically secret. Depending on the environment, values can
        appear in process environments, diagnostic output, crash reports,
        container metadata, service configuration, or inherited child
        processes.

        Use a dedicated secret-management mechanism when strong secret
        protection is required.
        """
    )

    show_command("export APP_ENV=production")
    show_command("printf '%s\\n' \"$APP_ENV\"")
    show_command("env | grep '^APP_'")

    explain(
        """
        Never print credentials merely to verify that they were loaded. Check
        presence, format, or access behavior without exposing the secret value.
        """)


# ============================================================================
# SECTION 64: INTERACTIVE VS NON-INTERACTIVE SHELL
# ============================================================================

def interactive_vs_noninteractive() -> None:
    print_title("63. Interactive and non-interactive Bash")

    explain(
        """
        An interactive shell reads commands for direct user interaction.
        A non-interactive shell commonly executes a script or a command
        supplied to bash -c.

        Startup-file behavior differs between interactive and non-interactive
        shells. A script should not assume that the user's interactive aliases,
        functions, PATH modifications, or configuration are available.
        """
    )

    show_command("bash")
    show_command("bash script.sh")
    show_command("bash -c 'printf \"%s\\n\" \"$PWD\"'")
    show_command("bash -ic 'alias'")

    explain(
        """
        Automation should explicitly establish the environment it needs rather
        than relying on personal shell configuration.
        """)


# ============================================================================
# SECTION 65: SHEBANG AND INTERPRETER CHOICE
# ============================================================================

def interpreter_choice() -> None:
    print_title("64. Interpreter choice and shebang behavior")

    explain(
        """
        The shebang is a convention that tells the operating system which
        interpreter should execute a script when the script itself is invoked
        as an executable.

        A Bash-specific script should request Bash. A POSIX shell script should
        request an appropriate POSIX shell. Python, Perl, and other languages
        have their own interpreter conventions.
        """
    )

    show_command("#!/usr/bin/env bash")
    show_command("#!/bin/sh")
    show_command("chmod +x script.sh")
    show_command("./script.sh")


# ============================================================================
# SECTION 66: EXIT STATUS DESIGN
# ============================================================================

def exit_status_design() -> None:
    print_title("65. Exit-status design")

    explain(
        """
        Exit statuses allow shell scripts and external automation systems to
        distinguish success from failure.

        Conventionally:
        0       success
        1-255   various failure or condition codes

        A script should use meaningful nonzero statuses when callers need to
        distinguish different failure classes. Avoid accidentally replacing a
        meaningful failure status with the status of an unrelated final command.
        """
    )

    show_command("exit 0", "Successful completion.")
    show_command("exit 1", "Generic failure.")
    show_command("exit 2", "Another failure category chosen by the script.")
    show_command("command || exit 1", "Stop when a required command fails.")

    explain(
        """
        Programs may reserve particular status values for particular meanings,
        so reusable automation should document the statuses it emits.
        """)


# ============================================================================
# SECTION 67: TESTING
# ============================================================================

def testing() -> None:
    print_title("66. Testing Bash scripts")

    explain(
        """
        Shell scripts should be tested with normal inputs, missing inputs,
        malformed inputs, empty files, filenames containing spaces, unusual
        filenames, permission failures, unavailable commands, interrupted
        execution, and partial failures.

        Syntax checking and tracing are useful but do not replace behavioral
        tests.
        """
    )

    test_cases = [
        "No arguments",
        "One normal argument",
        "An argument containing spaces",
        "An empty argument",
        "A nonexistent file",
        "A directory instead of a file",
        "Insufficient permissions",
        "Missing external command",
        "Interrupted execution",
        "Unexpected environment variables",
    ]

    for case in test_cases:
        print(f"  - {case}")

    show_command("bash -n script.sh")
    show_command("bash -x script.sh")
    show_command("./script.sh 'value with spaces'")


# ============================================================================
# SECTION 68: DOCUMENTATION
# ============================================================================

def documentation() -> None:
    print_title("67. Documenting shell scripts")

    explain(
        """
        Good documentation states what the script does, required inputs,
        expected environment, external dependencies, output, exit statuses,
        side effects, privileges, configuration, and recovery behavior.

        Avoid comments that merely restate obvious syntax. Comments are most
        valuable when they explain intent, assumptions, safety constraints, or
        non-obvious implementation decisions.
        """
    )

    print(
        r'''# Purpose
#   Rotate application logs and retain the most recent seven archives.
#
# Requirements
#   Bash 5.x
#   tar
#   gzip
#
# Inputs
#   Optional application directory as $1.
#
# Exit status
#   0 = success
#   1 = validation or operational failure
#
# Security
#   Requires write access to the configured archive directory.'''
    )


# ============================================================================
# SECTION 69: SAFE COMMAND EXECUTION FROM PYTHON
# ============================================================================

def python_command_execution() -> None:
    print_title("68. Executing Linux commands safely from Python")

    explain(
        """
        Python programs sometimes need to invoke operating-system commands.
        The subprocess module provides controlled process execution.

        Passing a list of arguments with shell=False avoids unnecessary shell
        parsing. If shell=True is required for a legitimate shell feature,
        never concatenate untrusted input into the command string.
        """
    )

    print(
        """Example:

import subprocess

result = subprocess.run(
    ["printf", "%s\\\\n", "hello"],
    text=True,
    capture_output=True,
    check=True,
    shell=False,
)

print(result.stdout)
"""
    )

    demonstrate(
        ["printf", "%s\\n", "Python invoking a Linux command"],
        "This script uses subprocess with an argument list and shell=False.",
    )


# ============================================================================
# SECTION 70: COMMAND EQUIVALENCE
# ============================================================================

def command_comparisons() -> None:
    print_title("69. Important command comparisons")

    comparisons = [
        (
            "find",
            "Filesystem search",
            "Can filter by many filesystem attributes and execute actions.",
        ),
        (
            "grep",
            "Text search",
            "Finds lines matching patterns in text streams/files.",
        ),
        (
            "locate",
            "Filename database search",
            "Fast lookup against an index that may not be current.",
        ),
        (
            "which",
            "Executable lookup",
            "Often less informative than Bash's command -v/type.",
        ),
        (
            "du",
            "Directory/file usage",
            "Estimates space consumed by filesystem entries.",
        ),
        (
            "df",
            "Filesystem capacity",
            "Reports free/used filesystem space.",
        ),
        (
            "ps",
            "Process snapshot",
            "Shows process state at a point in time.",
        ),
        (
            "top",
            "Live process monitoring",
            "Continuously refreshes process/resource information.",
        ),
        (
            "systemctl",
            "Service manager interface",
            "Controls and inspects systemd units.",
        ),
    ]

    print(f"{'Command':<15} {'Primary role':<28} Description")
    print("-" * 78)

    for command, role, description in comparisons:
        print(f"{command:<15} {role:<28} {description}")


# ============================================================================
# SECTION 71: MINI ADMINISTRATION WORKFLOW
# ============================================================================

def mini_administration_workflow() -> None:
    print_title("70. Mini administration workflow")

    explain(
        """
        A useful operational sequence is to inspect before changing anything.
        The following sequence demonstrates a read-only diagnostic workflow.
        """
    )

    commands = [
        "hostname",
        "uname -a",
        "uptime",
        "id",
        "pwd",
        "df -h",
        "free -h",
        "ps -p $$ -o pid,ppid,comm",
        "ip route",
    ]

    for command in commands:
        show_command(command)

    if platform.system() == "Linux":
        demonstrate(["hostname"], "Identify the host.")
        demonstrate(["uptime"], "Inspect uptime/load.")
        demonstrate(["id"], "Inspect current identity.")
        demonstrate(["df", "-h"], "Inspect filesystem capacity.")


# ============================================================================
# SECTION 72: PRACTICAL TROUBLESHOOTING
# ============================================================================

def troubleshooting() -> None:
    print_title("71. Troubleshooting checklist")

    scenarios = [
        (
            "command not found",
            [
                "type command_name",
                "command -v command_name",
                'printf "%s\\n" "$PATH"',
            ],
        ),
        (
            "permission denied",
            [
                "ls -l target",
                "id",
                "namei -l /path/to/target",
            ],
        ),
        (
            "disk full",
            [
                "df -h",
                "df -i",
                "du -xhd1 /path",
            ],
        ),
        (
            "process using too much CPU",
            [
                "ps aux --sort=-%cpu | head",
                "top",
            ],
        ),
        (
            "service not working",
            [
                "systemctl status SERVICE",
                "journalctl -u SERVICE --since today",
            ],
        ),
        (
            "network problem",
            [
                "ip addr",
                "ip route",
                "ss -tuln",
                "curl -I https://example.com",
            ],
        ),
    ]

    for scenario, commands in scenarios:
        print(f"\n{scenario}:")
        for command in commands:
            print(f"  $ {command}")


# ============================================================================
# SECTION 73: REAL-WORLD APPLICATIONS
# ============================================================================

def applications() -> None:
    print_title("72. Real-world Linux command-line applications")

    applications_list = [
        "Server administration",
        "Application deployment",
        "Log analysis",
        "Backup and restore workflows",
        "Data extraction and transformation",
        "Software development",
        "Build automation",
        "Continuous integration",
        "Container operations",
        "Cloud infrastructure administration",
        "Database maintenance",
        "Network troubleshooting",
        "Security auditing",
        "File synchronization",
        "Monitoring and incident response",
        "Scheduled automation",
        "System diagnostics",
    ]

    for application in applications_list:
        print(f"  - {application}")


# ============================================================================
# SECTION 74: QUICK REFERENCE
# ============================================================================

def quick_reference() -> None:
    print_title("73. Linux command-line quick reference")

    reference = {
        "Navigation": "pwd, ls, cd, pushd, popd",
        "Files": "touch, cp, mv, rm, mkdir, rmdir",
        "Inspection": "cat, less, head, tail, file, stat, wc",
        "Search": "find, grep, locate, command -v, type",
        "Text": "cut, tr, sort, uniq, sed, awk, paste, xargs",
        "Permissions": "chmod, chown, chgrp, umask",
        "Processes": "ps, top, pgrep, kill, jobs, fg, bg",
        "System": "uname, uptime, free, df, du, lsblk, lscpu",
        "Networking": "ip, ss, ping, curl, dig",
        "Archives": "tar, gzip, gunzip",
        "Services": "systemctl, journalctl",
        "Scheduling": "crontab",
        "Environment": "env, export, printenv",
        "Shell": "bash, set, shopt, read, trap",
    }

    for category, commands in reference.items():
        print(f"{category:<15}: {commands}")


# ============================================================================
# SECTION 75: KNOWLEDGE CHECK
# ============================================================================

def knowledge_check() -> None:
    print_title("74. Knowledge-check questions")

    questions = [
        "What is the difference between a shell and a terminal?",
        "What is the difference between an absolute and relative path?",
        "What do . and .. represent?",
        "What is the difference between > and >>?",
        "What are file descriptors 0, 1, and 2?",
        "How does a pipe connect two commands?",
        "How does grep differ from find?",
        "Why should ls output generally not be parsed?",
        "What is the difference between shell globbing and regular expressions?",
        "What does chmod 755 mean?",
        "What is the difference between a hard link and a symbolic link?",
        "What is an exit status?",
        "Why is quoting variable expansions important?",
        "Why is eval dangerous with untrusted input?",
        "What is the difference between stdout and stderr?",
        "What does set -o pipefail change?",
        "Why is "$@" usually preferred to "$*"?",
        "What is the purpose of trap?",
        "Why should predictable temporary filenames be avoided?",
        "When should a task be implemented in a general-purpose language instead of Bash?",
    ]

    for index, question in enumerate(questions, start=1):
        print(f"{index:2}. {question}")


# ============================================================================
# SECTION 76: SAFE LOCAL FILE DEMONSTRATION
# ============================================================================

def local_file_demonstration() -> None:
    print_title("75. Python-side filesystem demonstration")

    explain(
        """
        The following demonstration uses Python's pathlib module to show
        concepts that correspond to Linux filesystem operations. It creates
        objects only inside a temporary directory and removes that directory
        automatically when the demonstration ends.
        """
    )

    import tempfile

    with tempfile.TemporaryDirectory(prefix="linux_cli_demo_") as temp_dir:
        root = Path(temp_dir)
        source = root / "source.txt"
        copied = root / "copied.txt"
        nested = root / "nested"

        source.write_text("Linux\nBash\nCommand Line\n", encoding="utf-8")
        nested.mkdir()
        shutil.copy2(source, copied)

        print(f"  Temporary directory: {root}")
        print(f"  Source exists: {source.exists()}")
        print(f"  Copy exists: {copied.exists()}")
        print(f"  Nested directory exists: {nested.exists()}")
        print(f"  Source content: {source.read_text(encoding='utf-8').strip()}")

    print("  Temporary demonstration data was removed automatically.")


# ============================================================================
# SECTION 77: ENVIRONMENT INSPECTION
# ============================================================================

def environment_inspection() -> None:
    print_title("76. Inspecting the current Python execution environment")

    print(f"Operating system: {platform.system()}")
    print(f"Platform: {platform.platform()}")
    print(f"Python version: {platform.python_version()}")
    print(f"Current directory: {Path.cwd()}")
    print(f"Home directory: {Path.home()}")

    print("\nSelected environment variables:")
    for name in ["HOME", "USER", "SHELL", "PATH", "LANG", "PWD"]:
        value = os.environ.get(name)
        if value is None:
            print(f"  {name}: <not set>")
        elif name == "PATH":
            print(f"  {name}: {value[:160]}{'...' if len(value) > 160 else ''}")
        else:
            print(f"  {name}: {value}")


# ============================================================================
# SECTION 78: COMMAND AVAILABILITY
# ============================================================================

def command_availability() -> None:
    print_title("77. Checking common command availability")

    commands = [
        "bash",
        "ls",
        "grep",
        "find",
        "sed",
        "awk",
        "tar",
        "curl",
        "python3",
        "git",
        "ssh",
    ]

    for command in commands:
        location = shutil.which(command)
        print(f"  {command:<10} {location or '<not found>'}")


# ============================================================================
# SECTION 79: CONCEPTUAL MAP
# ============================================================================

def conceptual_map() -> None:
    print_title("78. Conceptual map of the Linux command line")

    print(
        """
    User
      |
      v
    Terminal
      |
      v
    Bash shell
      |
      +--> parsing
      |
      +--> expansion
      |      +--> variables
      |      +--> command substitution
      |      +--> pathname expansion
      |      +--> quoting rules
      |
      +--> command resolution
      |      +--> aliases
      |      +--> functions
      |      +--> builtins
      |      +--> PATH executables
      |
      +--> process creation
      |
      +--> standard streams
      |      +--> stdin
      |      +--> stdout
      |      +--> stderr
      |
      +--> redirection
      |
      +--> pipelines
      |
      +--> filesystem
      |
      +--> processes
      |
      +--> networking
      |
      +--> services
      |
      +--> automation
    """
    )


# ============================================================================
# SECTION 80: MAIN PROGRAM
# ============================================================================

def main() -> None:
    """Run every educational section in a logical learning order."""
    sections = [
        fundamentals,
        navigation,
        file_operations,
        file_content,
        expansion_and_wildcards,
        redirection_and_pipes,
        search_commands,
        text_processing,
        regular_expressions,
        permissions,
        links,
        processes,
        job_control,
        system_commands,
        environment_variables,
        command_substitution_and_exit_status,
        bash_scripting_basics,
        variables_arrays_parameters,
        conditions,
        loops_and_functions,
        input_validation,
        xargs,
        archives_and_compression,
        networking,
        package_management,
        services,
        scheduling,
        file_descriptors,
        process_substitution,
        grouping,
        shell_options,
        debugging,
        temporary_files,
        performance,
        portability,
        aliases,
        history,
        practical_combinations,
        log_processing_example,
        csv_processing_example,
        backup_workflow,
        security,
        root_and_sudo,
        script_quality,
        avoid_parsing_ls,
        common_mistakes,
        limitations_and_tradeoffs,
        production_design,
        advanced_pipeline_status,
        signal_safe_cleanup,
        command_discovery,
        builtins_vs_external,
        command_substitution_edge_cases,
        word_splitting,
        glob_safety,
        arithmetic,
        read_and_ifs,
        named_pipes,
        filesystem_concepts,
        proc_and_sys,
        storage,
        environment_security,
        interactive_vs_noninteractive,
        interpreter_choice,
        exit_status_design,
        testing,
        documentation,
        python_command_execution,
        command_comparisons,
        mini_administration_workflow,
        troubleshooting,
        applications,
        quick_reference,
        knowledge_check,
        local_file_demonstration,
        environment_inspection,
        command_availability,
        conceptual_map,
    ]

    print("=" * 78)
    print("LINUX COMMAND LINE AND BASH")
    print("Comprehensive beginner-to-advanced study script")
    print("=" * 78)
    print(f"Running on: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(f"Current directory: {Path.cwd()}")

    if platform.system() != "Linux":
        print(
            "\nNote: Linux-specific command demonstrations will be displayed "
            "but commands requiring Linux are not executed on this system."
        )

    for section in sections:
        try:
            section()
        except KeyboardInterrupt:
            print("\n\nExecution interrupted by the user.")
            break
        except Exception as error:
            # One failed demonstration should not prevent the educational
            # sections after it from being displayed.
            print(
                f"\n[Section error handled safely: "
                f"{type(error).__name__}: {error}]"
            )

    print_title("End of Linux command-line study script")
    print(
        "The examples above cover navigation, filesystem operations, "
        "search, text processing, Bash scripting, system administration, "
        "security, debugging, and production-oriented shell practices."
    )


if __name__ == "__main__":
    main()
