# Linux installation and environment

## Introduction

Linux is an open-source operating system family widely used for servers, cloud infrastructure, software development, cybersecurity, networking, containers, embedded systems, and high-performance computing.

This guide focuses on building a Linux environment from the ground up using a virtual machine, installing Ubuntu, learning the terminal, understanding the Linux filesystem, configuring users and permissions, and connecting to a remote Linux server through SSH.

The practical environment covered here uses:

- VirtualBox for virtualization
- Ubuntu as the Linux distribution
- Linux Terminal for command-line administration
- OpenSSH for secure remote access
- A local virtual machine for experimentation
- A remote Linux server as a production-style environment

The objective is to understand not only which commands to type, but also what the commands do, why they are required, how Linux organizes its environment, and how local and remote administration differ.

---

## Linux and operating systems

An operating system manages the relationship between computer hardware and software.

A simplified Linux environment can be viewed as:

    Applications
         │
         ▼
    Shell and command-line tools
         │
         ▼
    System libraries
         │
         ▼
    Linux kernel
         │
         ▼
    Hardware

The Linux kernel manages fundamental system resources such as:

- CPU scheduling
- Memory
- Processes
- Filesystems
- Devices
- Networking
- Security boundaries

Linux itself refers primarily to the kernel. Complete operating systems built around the Linux kernel are commonly called Linux distributions.

Examples include:

- Ubuntu
- Debian
- Fedora
- Rocky Linux
- AlmaLinux
- Arch Linux
- openSUSE

Ubuntu is based on Debian and is widely used for development, servers, cloud environments, and learning.

---

## Virtual machines

A virtual machine is a software-defined computer running inside another computer.

The physical computer is called the host.

The virtual computer is called the guest.

    Physical computer
    └── Host operating system
        └── VirtualBox
            └── Ubuntu virtual machine
                ├── Virtual CPU
                ├── Virtual RAM
                ├── Virtual disk
                ├── Virtual network adapter
                └── Ubuntu Linux

The guest operating system behaves like an independent computer while sharing physical resources with the host.

### Why use a virtual machine?

Virtual machines are useful because they allow Linux to be installed without replacing the existing operating system.

They provide:

- Isolation
- Safe experimentation
- Reproducibility
- Snapshots
- Virtual networking
- Independent storage
- Easy deletion and recreation

A virtual machine is especially useful when learning system administration because commands can be tested without directly modifying the host operating system.

---

## VirtualBox concepts

VirtualBox provides virtualization capabilities for desktop systems.

Important concepts include:

### Host

The physical computer running VirtualBox.

### Guest

The operating system running inside the virtual machine.

### Virtual CPU

CPU capacity assigned to the virtual machine.

### Virtual memory

RAM allocated to the virtual machine.

### Virtual disk

A file on the host that behaves like a disk inside the guest.

### ISO image

An ISO file is a disk-image representation commonly used to install an operating system.

For Ubuntu installation, the Ubuntu ISO acts as virtual installation media.

### Network adapter

A virtual network interface allows the guest operating system to communicate with the host, local network, or internet.

---

## Virtual machine resource allocation

A virtual machine should not consume all host resources.

For a basic Ubuntu learning environment, a reasonable configuration can be:

| Resource | Typical learning configuration |
|---|---|
| CPU | 2 virtual CPUs |
| RAM | 4 GB |
| Storage | 25 GB or more |
| Network | NAT |
| Graphics | Default VirtualBox configuration |
| Boot media | Ubuntu ISO |

The appropriate configuration depends on the host computer.

Allocating more virtual CPUs or RAM does not automatically make the virtual machine faster. The host operating system still needs sufficient resources.

---

## Installing Ubuntu in VirtualBox

The general installation process is:

1. Install VirtualBox on the host.
2. Download an Ubuntu ISO image.
3. Create a new virtual machine.
4. Select Linux and Ubuntu as the operating system family.
5. Allocate RAM and CPUs.
6. Create a virtual disk.
7. Attach the Ubuntu ISO.
8. Start the virtual machine.
9. Follow the Ubuntu installer.
10. Create a user account.
11. Complete installation.
12. Restart the virtual machine.
13. Remove the installation ISO if necessary.

After installation, Ubuntu starts as an independent guest operating system.

---

## The Linux terminal

The terminal provides a text-based interface to the operating system.

A terminal application provides the interface, while a shell interprets commands.

Common shells include:

- Bash
- Zsh
- Fish
- Dash

Ubuntu commonly uses Bash as the default interactive shell in many installations.

The relationship can be represented as:

    User
      │
      ▼
    Terminal application
      │
      ▼
    Shell
      │
      ▼
    Linux commands
      │
      ▼
    Kernel / operating system

The terminal is not the shell itself.

A terminal is an interface application.

The shell is the command interpreter.

---

## The command prompt

A typical Linux prompt may look similar to:

    atul@ubuntu:~$

The components commonly indicate:

    atul       → username
    ubuntu     → hostname
    ~          → current directory
    $          → regular user prompt

The root user commonly uses `#` instead of `$`.

---

## Basic terminal commands

### Print the current directory

    pwd

`pwd` means print working directory.

Example:

    /home/atul

### List files

    ls

Detailed listing:

    ls -l

Show hidden files:

    ls -a

Combine options:

    ls -la

### Change directory

    cd /tmp

Return to the previous directory:

    cd -

Move to the home directory:

    cd ~

Move one directory upward:

    cd ..

### Create a directory

    mkdir linux-lab

Create nested directories:

    mkdir -p projects/linux/scripts

### Create an empty file

    touch notes.txt

### Copy a file

    cp notes.txt backup.txt

### Move or rename a file

    mv notes.txt linux-notes.txt

### Delete a file

    rm linux-notes.txt

Remove an empty directory:

    rmdir linux-lab

Delete a directory recursively:

    rm -r linux-lab

Recursive deletion should be used carefully because Linux does not normally provide the same kind of recycle-bin protection expected from graphical file managers.

---

## Viewing file contents

### Print an entire file

    cat notes.txt

### Read a long file interactively

    less notes.txt

Useful controls in `less` include:

    Space  → next page
    b      → previous page
    /word  → search
    q      → quit

### Display the beginning

    head notes.txt

### Display the end

    tail notes.txt

Follow a changing log file:

    tail -f application.log

This is particularly useful for monitoring server logs.

---

## Command options

Linux commands commonly use options.

For example:

    ls

lists directory contents.

    ls -l

requests a long-format listing.

    ls -la

combines multiple options.

Many commands provide documentation through:

    command --help

For example:

    cp --help

Manual pages can be accessed using:

    man cp

Manual pages are an important part of Linux administration because command behavior, options, configuration files, and security implications can vary.

---

## Linux filesystem hierarchy

Linux uses a hierarchical filesystem beginning at `/`.

The root directory is represented by:

    /

Important directories include:

| Directory | Typical purpose |
|---|---|
| `/` | Filesystem root |
| `/home` | User home directories |
| `/root` | Root user's home directory |
| `/etc` | System configuration |
| `/var` | Variable data such as logs |
| `/tmp` | Temporary files |
| `/usr` | User-space programs and libraries |
| `/bin` | Essential executable programs |
| `/sbin` | System administration programs |
| `/opt` | Optional software |
| `/dev` | Device interfaces |
| `/proc` | Process and kernel information |
| `/sys` | Kernel and device information |
| `/boot` | Boot-related files |
| `/mnt` | Temporary mount points |
| `/media` | Removable media mount points |

The exact organization can vary by distribution and filesystem layout.

---

## Absolute and relative paths

An absolute path begins at `/`.

Example:

    /home/atul/projects/app

A relative path depends on the current working directory.

If the current directory is:

    /home/atul

then:

    projects/app

refers to:

    /home/atul/projects/app

Special path symbols include:

    .   current directory
    ..  parent directory
    ~   current user's home directory
    /   filesystem root

---

## Files versus directories

Linux treats many resources using a file-oriented model.

A directory contains references to filesystem objects.

Regular files can contain:

- Text
- Binary data
- Program code
- Configuration
- Logs

Other object types include:

- Directories
- Symbolic links
- Device files
- Named pipes
- Sockets

The `file` command can help identify a file type:

    file notes.txt

---

## Hidden files

Linux commonly considers filenames beginning with `.` to be hidden.

Examples:

    .bashrc
    .profile
    .gitconfig
    .ssh

Use:

    ls -la

to display them.

Hidden does not mean secure.

A file beginning with `.` is simply excluded from normal directory listings.

---

## Environment variables

Environment variables store values that programs can access.

View all environment variables:

    env

Print one variable:

    echo "$HOME"

Common variables include:

    HOME
    PATH
    USER
    SHELL
    LANG
    PWD

The `PATH` variable determines directories searched when a command is entered without an explicit path.

Inspect it with:

    echo "$PATH"

A typical value resembles:

    /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

The colon separates directories.

---

## The PATH mechanism

When the user enters:

    python

the shell searches directories listed in `PATH`.

A command can be executed directly by providing its path:

    /usr/bin/python3

Find the executable selected by the shell:

    which python3

A more comprehensive command lookup is:

    type python3

The distinction matters because shell aliases, functions, built-ins, and executable files can have different resolution behavior.

---

## Standard input, output, and error

Linux processes commonly work with three standard streams:

    0 → stdin
    1 → stdout
    2 → stderr

Standard input provides data to a program.

Standard output contains normal program output.

Standard error contains error messages.

Redirect output to a file:

    ls > files.txt

Append instead of replacing:

    ls >> files.txt

Redirect errors:

    command 2> errors.txt

Redirect both output streams:

    command > output.txt 2>&1

---

## Pipes

A pipe sends the output of one command into the input of another.

Example:

    ls -la | less

Another example:

    ps aux | grep python

The conceptual flow is:

    ps aux
       │
       ▼
    stdout
       │
       │ pipe
       ▼
    grep python
       │
       ▼
    filtered output

Pipelines are one of the most important mechanisms in command-line Linux.

---

## Useful text-processing commands

### Search for text

    grep "ERROR" application.log

Recursive search:

    grep -R "database" .

### Count lines, words, and bytes

    wc notes.txt

Count lines:

    wc -l notes.txt

### Sort data

    sort names.txt

### Remove duplicate adjacent lines

    uniq names.txt

A common combination is:

    sort names.txt | uniq

### Search for files

    find . -name "*.log"

Search by type:

    find . -type f -name "*.py"

---

## Installing software

Ubuntu commonly uses the Advanced Package Tool ecosystem.

Update package metadata:

    sudo apt update

Upgrade installed packages:

    sudo apt upgrade

Install a package:

    sudo apt install curl

Remove a package:

    sudo apt remove curl

Search packages:

    apt search package-name

The distinction between updating package metadata and upgrading packages is important.

    apt update

refreshes information about available packages.

    apt upgrade

installs newer versions of installed packages when available.

---

## sudo and administrative privileges

Linux separates ordinary users from privileged operations.

`sudo` allows an authorized user to execute a command with elevated privileges.

Example:

    sudo apt update

The command following `sudo` executes with elevated privileges.

Administrative access should be used only when required.

Running an unnecessary command with `sudo` can increase the potential impact of mistakes.

Avoid:

    sudo rm -rf ...

unless the exact target and consequences are completely understood.

---

## Users and groups

Linux supports multiple users and groups.

Display the current user:

    whoami

Display identity and group information:

    id

Display groups:

    groups

Users can belong to groups that provide access to resources.

This model is important for:

- File permissions
- Shared directories
- Administrative access
- Service accounts
- Application isolation

---

## File permissions

Linux permissions are commonly displayed using a structure similar to:

    -rwxr-xr--

The first character represents the file type.

The remaining characters represent permissions for:

    owner
    group
    others

The three basic permissions are:

    r → read
    w → write
    x → execute

For example:

    rwxr-xr--

means:

    Owner  → rwx
    Group  → r-x
    Others → r--

---

## Numeric permissions

Permissions can also be represented numerically.

Values are:

    read    = 4
    write   = 2
    execute = 1

Therefore:

    rwx = 7
    r-x = 5
    r-- = 4

Example:

    chmod 755 script.sh

means:

    Owner  → 7 → rwx
    Group  → 5 → r-x
    Others → 5 → r-x

A more restrictive example:

    chmod 600 private.txt

means:

    Owner  → read + write
    Group  → no permissions
    Others → no permissions

---

## chmod

`chmod` changes permissions.

Symbolic form:

    chmod u+x script.sh

This adds execute permission for the owner.

Remove write permission from others:

    chmod o-w file.txt

Numeric form:

    chmod 644 document.txt

Permissions should be selected according to the actual access requirement rather than using broad permissions by default.

---

## Ownership

Inspect ownership:

    ls -l

Change ownership:

    sudo chown user:user file.txt

Change group:

    sudo chgrp developers file.txt

Ownership and permissions work together.

A user may have permission through:

- File ownership
- Group membership
- Other permissions
- ACLs
- Additional security mechanisms

---

## Processes

A process is a running instance of a program.

List processes:

    ps

Show processes for all users:

    ps aux

Interactive process monitoring:

    top

Depending on the system, `htop` may provide a more user-friendly interface.

Find a process:

    pgrep python

Terminate a process gracefully:

    kill PID

A stronger termination signal can be sent using:

    kill -9 PID

`SIGKILL` should not be the default choice because it prevents the process from performing normal cleanup.

---

## Process IDs

Every process normally has a process identifier called a PID.

Example:

    PID    COMMAND
    1201   sshd
    1832   python

The PID allows administrative commands to target a specific process.

The special PID:

    1

belongs to the initial userspace process, commonly `systemd` on modern Ubuntu installations.

---

## Background processes

A command can be started in the background using:

    command &

Example:

    sleep 60 &

List shell jobs:

    jobs

Bring a job to the foreground:

    fg

Suspend a foreground command with:

    Ctrl+Z

Continue it in the background:

    bg

---

## Services and systemd

Modern Ubuntu installations commonly use `systemd` for service and system management.

Check a service:

    systemctl status ssh

Start a service:

    sudo systemctl start ssh

Stop a service:

    sudo systemctl stop ssh

Restart a service:

    sudo systemctl restart ssh

Enable a service at boot:

    sudo systemctl enable ssh

Disable automatic startup:

    sudo systemctl disable ssh

The distinction between a process and a service is important.

A process is a running execution instance.

A service is typically a managed background component with lifecycle and startup configuration.

---

## System logs

Ubuntu commonly stores logs under:

    /var/log

Examples include authentication and system logs.

Systemd-based systems also provide:

    journalctl

View recent logs:

    journalctl

View logs for a service:

    journalctl -u ssh

Follow logs in real time:

    journalctl -u ssh -f

Logs are essential for diagnosing failed services, authentication problems, networking issues, and application failures.

---

## Networking fundamentals

A Linux machine can have one or more network interfaces.

Inspect interfaces:

    ip addr

Inspect routes:

    ip route

Test connectivity:

    ping 8.8.8.8

Resolve a domain:

    getent hosts example.com

Test a service port:

    nc -vz example.com 443

The `ip` command is the modern general-purpose tool for inspecting and managing many Linux networking components.

---

## IP addresses

An IP address identifies a network interface within an IP network.

IPv4 addresses contain four decimal components.

Example:

    192.168.1.20

A private IPv4 address is commonly used inside local networks.

Common private ranges include:

    10.0.0.0/8
    172.16.0.0/12
    192.168.0.0/16

A virtual machine may receive a private IP depending on its VirtualBox networking mode.

---

## VirtualBox networking modes

Common VirtualBox networking configurations include:

### NAT

The guest accesses external networks through the host.

It is convenient and relatively isolated.

### Bridged adapter

The guest appears more like another device on the local network.

It can receive an address from the local network's DHCP infrastructure.

### Host-only adapter

The guest communicates with the host and potentially other host-only guests without necessarily having normal internet access.

### Internal network

Virtual machines can communicate with each other on an isolated virtual network.

The appropriate mode depends on the desired topology.

---

## SSH

SSH means Secure Shell.

It provides encrypted remote access to another computer.

The basic model is:

    Local computer
         │
         │ encrypted SSH connection
         ▼
    Remote Linux server
         │
         ▼
    Remote shell

SSH is commonly used for:

- Server administration
- Remote development
- File transfers
- Automation
- Git operations
- Infrastructure management
- Cloud server access

---

## SSH client and server

SSH uses a client-server architecture.

The local machine runs an SSH client.

The remote machine runs an SSH server, commonly called `sshd`.

The client initiates the connection.

The server authenticates the user and provides the requested session.

---

## Installing the SSH server

On Ubuntu, the OpenSSH server package can be installed using:

    sudo apt update
    sudo apt install openssh-server

Check its status:

    sudo systemctl status ssh

If required:

    sudo systemctl start ssh

Enable startup:

    sudo systemctl enable ssh

---

## Finding the server IP

On the Ubuntu machine:

    ip addr

Look for the address assigned to the relevant network interface.

Another useful command is:

    hostname -I

The address shown depends on the network configuration.

---

## Basic SSH connection

The general syntax is:

    ssh username@server_ip

Example:

    ssh atul@192.168.56.101

If SSH uses a non-default port:

    ssh -p 2222 atul@192.168.56.101

The first connection may display a host authenticity prompt.

This is related to SSH host-key verification.

---

## SSH host keys

SSH servers possess cryptographic host keys.

The client uses these keys to identify the server.

After a successful first connection, the server's host key can be stored in the local:

    ~/.ssh/known_hosts

If the same host later presents a different key, SSH may issue a warning.

A changed host key can have legitimate causes, such as:

- Server reinstallation
- Host replacement
- Key regeneration

It can also indicate a security problem such as a man-in-the-middle attack.

Host-key warnings should not be ignored automatically.

---

## Password authentication

SSH can authenticate users with passwords.

Example:

    ssh username@server_ip

The server requests the account password if password authentication is enabled.

Password authentication is easy to understand but can be vulnerable to:

- Password guessing
- Credential reuse
- Brute-force attacks
- Credential theft

For administrative environments, SSH keys are generally preferred.

---

## SSH key authentication

SSH keys use asymmetric cryptography.

A key pair contains:

    Private key → kept secret
    Public key  → installed on the server

The private key should never be shared.

The public key can be placed in the user's:

    ~/.ssh/authorized_keys

on the remote server.

The authentication model is:

    Client
    ├── private key
    │
    └─────────────── authentication proof
                             │
                             ▼
                        SSH server
                             │
                        public key

The private key proves possession without sending the private key itself to the server.

---

## Generating an SSH key

A modern command is:

    ssh-keygen -t ed25519

The command normally creates files under:

    ~/.ssh/

The private key and public key should be protected appropriately.

Typical names may resemble:

    id_ed25519
    id_ed25519.pub

The `.pub` file is the public key.

The file without `.pub` is the private key.

---

## Copying a public key to a server

A convenient command is:

    ssh-copy-id username@server_ip

After the public key is installed, the client can authenticate using the private key.

If `ssh-copy-id` is unavailable, the public key can be added manually to:

    ~/.ssh/authorized_keys

on the server.

---

## SSH directory permissions

SSH is sensitive to filesystem permissions.

A typical configuration is:

    chmod 700 ~/.ssh
    chmod 600 ~/.ssh/authorized_keys

The private key should also have restrictive permissions:

    chmod 600 ~/.ssh/id_ed25519

Excessively permissive SSH files can cause authentication failures or security risks.

---

## SSH configuration

SSH client settings can be stored in:

    ~/.ssh/config

For example, a conceptual configuration may define:

    Host myserver
        HostName 192.168.56.101
        User atul
        IdentityFile ~/.ssh/id_ed25519

Then the connection can be shortened to:

    ssh myserver

This is useful when managing multiple servers.

---

## SSH troubleshooting

Verbose SSH output can be enabled with:

    ssh -v username@server_ip

More verbosity:

    ssh -vv username@server_ip

Maximum diagnostic verbosity:

    ssh -vvv username@server_ip

Common problems include:

| Problem | Possible cause |
|---|---|
| Connection refused | SSH server not listening |
| Connection timed out | Firewall or routing problem |
| Permission denied | Authentication failure |
| Host key warning | Changed server identity |
| No route to host | Network configuration |
| Name resolution failure | DNS problem |
| Key rejected | Wrong key or permissions |

A systematic troubleshooting process should determine whether the failure occurs at:

    DNS
      ↓
    Network route
      ↓
    TCP port
      ↓
    SSH service
      ↓
    Host-key verification
      ↓
    Authentication
      ↓
    Authorization
      ↓
    Shell/session

---

## SSH port

SSH commonly listens on TCP port:

    22

The actual configured port can differ.

Check listening sockets with:

    sudo ss -tlnp

The port should not be changed merely for security through obscurity. Strong authentication, key management, firewall rules, monitoring, and timely updates are more important security controls.

---

## Firewalls

Ubuntu systems may use `ufw` as a convenient firewall interface.

Check status:

    sudo ufw status

Allow SSH:

    sudo ufw allow ssh

Enable the firewall:

    sudo ufw enable

Firewall changes should be planned carefully on remote systems.

A poorly configured firewall can lock administrators out.

---

## SSH security practices

Important SSH security practices include:

- Protect private keys.
- Use strong authentication.
- Prefer key-based authentication.
- Use passphrases for private keys.
- Remove unused accounts.
- Remove unused authorized keys.
- Keep the SSH server updated.
- Restrict network access where practical.
- Use firewall rules.
- Monitor authentication logs.
- Avoid sharing private keys.
- Verify host keys.
- Use least privilege.
- Consider disabling password authentication after confirming key authentication works.

If disabling password authentication remotely, confirm that another authentication method works before ending the current session.

---

## SSH agent

An SSH agent can hold decrypted private keys in memory.

Start an agent:

    eval "$(ssh-agent -s)"

Add a key:

    ssh-add ~/.ssh/id_ed25519

List loaded keys:

    ssh-add -l

An agent reduces repeated passphrase entry while avoiding the need to store an unencrypted private key.

---

## SSH file transfer

Secure copy can transfer files using SSH.

Upload:

    scp local.txt username@server_ip:/home/username/

Download:

    scp username@server_ip:/home/username/remote.txt .

Recursive directory transfer:

    scp -r project username@server_ip:/home/username/

For larger or repeated synchronization tasks, `rsync` is often more efficient.

---

## rsync

A typical remote synchronization command is:

    rsync -av project/ username@server_ip:/home/username/project/

The `-a` option enables archive-style synchronization.

The `-v` option enables verbose output.

A trailing slash has semantic importance.

Compare:

    project/

with:

    project

because the source directory contents and directory itself can be handled differently.

Always test destructive synchronization commands carefully.

---

## Shell scripting

Shell commands can be combined into scripts.

Example:

    #!/usr/bin/env bash

    set -e

    echo "Current user:"
    whoami

    echo "Current directory:"
    pwd

    echo "System information:"
    uname -a

The first line is called a shebang.

It tells the operating system which interpreter should execute the script.

Make the script executable:

    chmod +x system-info.sh

Run it:

    ./system-info.sh

---

## Exit status

Linux commands normally return an exit status.

Conventionally:

    0       → success
    nonzero → failure

Inspect the previous command's status:

    echo $?

Shell scripts can use this status to determine whether operations succeeded.

For example:

    if command; then
        echo "Command succeeded"
    else
        echo "Command failed"
    fi

Exit codes are important in automation and CI/CD systems.

---

## Command chaining

Run a second command only if the first succeeds:

    command1 && command2

Run a second command if the first fails:

    command1 || command2

Run commands sequentially regardless of success:

    command1 ; command2

These operators have different semantics and should not be treated as interchangeable.

---

## Environment configuration

Shell startup files configure the user's environment.

Common files include:

    ~/.bashrc
    ~/.profile

The appropriate file depends on shell type and login behavior.

Environment variables can be temporarily set:

    APP_ENV=development python3 app.py

They can also be exported:

    export APP_ENV=development

Then child processes can access the variable.

---

## Python on Linux

Python is commonly used on Linux for:

- Automation
- Administration
- Data processing
- Web development
- Testing
- DevOps
- Infrastructure tooling

Check Python:

    python3 --version

Find its location:

    which python3

Run Python:

    python3

The Linux environment and Python environment are related but distinct.

---

## Virtual environments

Python virtual environments isolate project dependencies.

Create one:

    python3 -m venv .venv

Activate it in Bash:

    source .venv/bin/activate

After activation, the prompt often changes.

Install packages:

    python -m pip install package-name

Deactivate:

    deactivate

Virtual environments are useful because two projects may require incompatible package versions.

---

## Package management comparison

Linux package management and Python package management solve different problems.

| System | Primary purpose |
|---|---|
| `apt` | Ubuntu system packages |
| `pip` | Python packages |
| `venv` | Python environment isolation |

A system package may contain:

- Executables
- Libraries
- Configuration
- Documentation
- Service definitions

A Python package primarily provides Python-level functionality.

Confusing these layers can lead to dependency and environment problems.

---

## Disk usage

Check filesystem capacity:

    df -h

Check directory or file size:

    du -sh .

Find large directories:

    du -h --max-depth=1

Disk capacity and disk usage are different concepts.

`df` examines filesystem-level available space.

`du` estimates space consumed by files and directories.

---

## Memory

Memory usage can be inspected with:

    free -h

Processes can be inspected with:

    top

Linux may use available memory for filesystem caching.

Therefore, a low amount of "free" memory does not automatically indicate a memory problem.

The more meaningful question is whether applications have sufficient available memory and whether swapping or memory pressure is occurring.

---

## CPU information

Inspect CPU information:

    lscpu

Inspect kernel information:

    uname -a

Check kernel release:

    uname -r

These commands help distinguish:

- CPU architecture
- Kernel version
- Operating system environment
- Virtualized hardware

---

## System information

Useful commands include:

    hostname

    hostnamectl

    uname -a

    lsb_release -a

Depending on the Ubuntu version, `/etc/os-release` can also provide distribution information:

    cat /etc/os-release

---

## Time and timezone

Linux systems maintain system time and timezone configuration.

Check time:

    date

Check timezone and clock status:

    timedatectl

Time synchronization is important for:

- Logs
- Authentication
- Certificates
- Distributed systems
- Databases
- Scheduled tasks

---

## Cron and scheduled tasks

Cron provides time-based job scheduling.

View a user's cron jobs:

    crontab -l

Edit them:

    crontab -e

A cron expression contains fields representing scheduling intervals.

A conceptual example:

    minute hour day-of-month month day-of-week command

A job intended to run every day at 02:30 could be represented as:

    30 2 * * * /home/atul/backup.sh

Cron jobs should use absolute paths and should log failures appropriately.

---

## Symbolic links

A symbolic link points to another path.

Create one:

    ln -s original.txt shortcut.txt

Inspect it:

    ls -l shortcut.txt

Symbolic links are useful for:

- Alternate paths
- Version switching
- Configuration management
- Application deployment

A symbolic link can become broken if its target is removed or moved.

---

## Hard links

A hard link refers to the same underlying filesystem inode as another directory entry.

Create one:

    ln original.txt second-name.txt

Hard links have different semantics from symbolic links.

Important distinctions include:

| Property | Symbolic link | Hard link |
|---|---|---|
| Points to | Path | Same inode |
| Can cross filesystems | Usually no | No |
| Can reference directories normally | Generally no | Generally restricted |
| Breaks when target path is removed | Yes | No, if another hard link exists |

---

## Inodes

An inode stores filesystem metadata associated with a file.

It can contain information such as:

- File type
- Permissions
- Ownership
- Timestamps
- Size
- References to data blocks

A directory entry maps a filename to an inode.

This explains why changing a filename does not necessarily mean the underlying file data has been recreated.

---

## File descriptors

A running process uses file descriptors to reference open files and other I/O resources.

The standard descriptors are:

    0 → stdin
    1 → stdout
    2 → stderr

Additional descriptors can represent:

- Regular files
- Sockets
- Pipes
- Devices

This abstraction allows many Linux programs to treat different resources through similar I/O mechanisms.

---

## SSH tunneling

SSH can forward network connections.

Local port forwarding can conceptually look like:

    Local application
          │
          ▼
    localhost:8080
          │
          │ SSH tunnel
          ▼
    Remote server
          │
          ▼
    remote-service:80

A typical command may be:

    ssh -L 8080:localhost:80 username@server

This tells SSH to listen locally on port 8080 and forward traffic through the SSH connection to the specified destination from the remote side.

SSH forwarding can be powerful and should be used only with systems and services the user is authorized to access.

---

## Remote server architecture

A typical production-style arrangement can be represented as:

    Developer computer
           │
           │ SSH
           ▼
    Internet / private network
           │
           ▼
    Linux server
           ├── SSH service
           ├── Application
           ├── Database
           ├── Logs
           ├── Firewall
           └── Monitoring

A cloud virtual machine is conceptually similar to a local VirtualBox guest, although the underlying infrastructure is very different.

---

## Production considerations

A Linux server should not be treated like a disposable learning VM.

Production environments require attention to:

- Authentication
- Authorization
- Network exposure
- Firewall configuration
- Patch management
- Logging
- Monitoring
- Backups
- Resource limits
- Secrets management
- Service dependencies
- Recovery procedures

A command that is harmless in a disposable VM may have serious consequences on a production system.

---

## Local virtual machine versus remote server

| Characteristic | VirtualBox VM | Remote server |
|---|---|---|
| Physical location | Local computer | Remote infrastructure |
| Access | Local console or network | Network |
| Networking | Virtualized | Physical/cloud network |
| Storage | Host-backed virtual disk | Server/cloud storage |
| Purpose | Learning/testing | Development/production |
| Failure impact | Usually local | Potentially service-wide |
| Access security | Lower exposure | Higher importance |

The commands used inside the Linux environment can often be very similar.

---

## Common Linux mistakes

### Running commands from the wrong directory

Always check:

    pwd

before performing filesystem operations.

### Deleting without verifying the target

Before using:

    rm

inspect the path carefully.

### Using sudo unnecessarily

Prefer ordinary privileges unless administrative permissions are required.

### Confusing relative and absolute paths

Verify the current directory with:

    pwd

### Assuming a command exists

Check:

    command -v command_name

### Ignoring exit codes

Check:

    echo $?

when debugging scripts.

### Copying commands without understanding them

Especially avoid blindly copying destructive commands involving:

    rm
    chmod
    chown
    dd
    mkfs
    mount
    systemctl
    iptables
    ufw

---

## Common SSH mistakes

### Using the wrong username

The Linux account name on the remote machine must be correct.

### Using the wrong IP address

Confirm the server's current address.

### SSH service not running

Check:

    sudo systemctl status ssh

### Port blocked

Check firewall configuration and listening ports.

### Incorrect private-key permissions

Use:

    chmod 600 ~/.ssh/id_ed25519

### Public key installed for the wrong user

The public key must be in the intended user's:

    ~/.ssh/authorized_keys

### Ignoring host-key warnings

Host identity changes should be investigated rather than automatically bypassed.

---

## Debugging methodology

Linux troubleshooting is most effective when performed in layers.

A useful order is:

    Application
        ↓
    Process
        ↓
    Service
        ↓
    Port
        ↓
    Network
        ↓
    Operating system
        ↓
    Virtual machine
        ↓
    Physical infrastructure

For SSH:

    Hostname/IP
        ↓
    Network route
        ↓
    TCP connectivity
        ↓
    SSH listener
        ↓
    Host key
        ↓
    Authentication
        ↓
    Authorization
        ↓
    Shell

Useful commands include:

    ping
    ip
    ss
    systemctl
    journalctl
    ps
    top
    df
    du
    free
    ls
    grep
    find
    ssh -vvv

The objective is to identify the first layer where the expected behavior fails.

---

## Security model

Linux security is based on multiple layers rather than a single feature.

Important mechanisms include:

    User identity
          ↓
    Group membership
          ↓
    File permissions
          ↓
    Process privileges
          ↓
    Network controls
          ↓
    Authentication
          ↓
    Authorization
          ↓
    Logging and monitoring

Modern Linux systems may also use mechanisms such as:

- AppArmor
- SELinux on distributions that use it
- Linux capabilities
- Namespaces
- cgroups
- Secure Boot
- Kernel security controls

Ubuntu commonly uses AppArmor as part of its security architecture.

---

## Least privilege

Least privilege means providing only the permissions required to perform a task.

For example, an application that only needs to read a configuration file should not automatically receive unrestricted write access to the entire filesystem.

Least privilege reduces the potential impact of:

- Bugs
- Compromised applications
- Stolen credentials
- Operator mistakes

---

## Secrets management

Private keys, passwords, API tokens, and other credentials should not be placed casually into:

- Public repositories
- Shell history
- World-readable files
- Application logs
- Shared documents

SSH private keys should remain private.

A production system should use an appropriate secrets-management strategy rather than embedding credentials directly into source code.

---

## Shell history

Bash commonly records commands in:

    ~/.bash_history

Avoid putting secrets directly into commands when possible.

For example, a command containing a password may become visible through shell history, process inspection, logs, or monitoring tools depending on the program and environment.

---

## Permissions and security trade-offs

Broad permissions are convenient but weaken isolation.

For example:

    chmod 777 file

gives read, write, and execute permissions to everyone for a regular file.

This is often inappropriate.

A better approach is to determine:

    Who needs access?
    What operation do they need?
    For how long?
    At what scope?

Then assign the minimum necessary permission.

---

## Performance considerations

Virtual machines introduce overhead because the guest operates through virtualization layers.

Performance depends on:

- CPU allocation
- RAM allocation
- Disk performance
- Virtual disk format
- Host workload
- Network configuration
- Guest configuration

A VM with insufficient RAM may experience swapping.

A VM with excessive allocation can starve the host.

Balanced resource allocation is generally more useful than maximizing every virtual resource.

---

## Linux performance diagnosis

Performance analysis should be evidence-driven.

CPU:

    top

Memory:

    free -h

Disk space:

    df -h

Directory usage:

    du -sh *

Network sockets:

    ss -tulpn

Processes:

    ps aux

The correct diagnostic command depends on the suspected bottleneck.

---

## Snapshots

VirtualBox snapshots preserve the state of a virtual machine at a point in time.

They can be useful before:

- Major configuration changes
- Package experiments
- Networking changes
- Permission experiments
- Service configuration changes

Snapshots are not a replacement for proper backups.

They depend on the host and virtualization environment and should not be treated as permanent disaster-recovery storage.

---

## Reproducible Linux environments

A manually configured machine is difficult to reproduce exactly.

Reproducibility improves when environments are documented or automated.

Relevant technologies in broader infrastructure workflows include:

- Shell scripts
- Configuration management
- Containers
- Infrastructure as code
- Virtual machine images
- CI/CD systems

The fundamental principle is to reduce undocumented manual configuration.

---

## Linux command reference

| Task | Command |
|---|---|
| Current directory | `pwd` |
| List files | `ls` |
| Detailed listing | `ls -la` |
| Change directory | `cd` |
| Create directory | `mkdir` |
| Create file | `touch` |
| Copy | `cp` |
| Move/rename | `mv` |
| Delete file | `rm` |
| Read file | `cat` |
| Page through file | `less` |
| Search text | `grep` |
| Find files | `find` |
| Current user | `whoami` |
| User identity | `id` |
| Processes | `ps aux` |
| Interactive processes | `top` |
| Network interfaces | `ip addr` |
| Routes | `ip route` |
| Listening ports | `ss -tlnp` |
| Filesystem space | `df -h` |
| Directory space | `du -sh` |
| Memory | `free -h` |
| Kernel version | `uname -r` |
| OS information | `cat /etc/os-release` |
| Service status | `systemctl status` |
| Service logs | `journalctl -u` |
| SSH connection | `ssh user@host` |
| SSH diagnostics | `ssh -vvv user@host` |
| Generate SSH key | `ssh-keygen -t ed25519` |
| Copy SSH key | `ssh-copy-id user@host` |
| Secure copy | `scp` |
| Synchronize files | `rsync` |

---

## Practical learning sequence

A useful hands-on progression is:

    Install VirtualBox
          ↓
    Create Ubuntu VM
          ↓
    Install Ubuntu
          ↓
    Open Terminal
          ↓
    Learn filesystem navigation
          ↓
    Create and manipulate files
          ↓
    Learn permissions
          ↓
    Learn users and groups
          ↓
    Install packages
          ↓
    Inspect processes
          ↓
    Manage services
          ↓
    Inspect networking
          ↓
    Install OpenSSH
          ↓
    Connect through SSH
          ↓
    Configure SSH keys
          ↓
    Transfer files
          ↓
    Troubleshoot SSH
          ↓
    Apply Linux security practices

This sequence moves from basic interaction toward real server administration.

---

## Hands-on laboratory

A safe local VM exercise can use the following commands.

Create a workspace:

    mkdir -p ~/linux-lab/{files,scripts,logs}
    cd ~/linux-lab

Create sample files:

    echo "Linux administration" > files/topic.txt
    echo "SSH fundamentals" >> files/topic.txt

Read the file:

    cat files/topic.txt

Inspect it:

    ls -l files/topic.txt
    file files/topic.txt

Search its contents:

    grep "SSH" files/topic.txt

Create a shell script:

    cat > scripts/system-info.sh <<'EOF'
    #!/usr/bin/env bash

    echo "User: $(whoami)"
    echo "Host: $(hostname)"
    echo "Directory: $(pwd)"
    echo "Kernel: $(uname -r)"
    EOF

Make it executable:

    chmod +x scripts/system-info.sh

Run it:

    ./scripts/system-info.sh

Inspect permissions:

    ls -l scripts/system-info.sh

Inspect system information:

    free -h
    df -h
    ip addr

This laboratory connects filesystem operations, permissions, scripting, system inspection, and networking.

---

## Advanced laboratory: SSH between two environments

A local VirtualBox setup can be used to simulate client-server architecture.

    Ubuntu client VM
          │
          │ SSH
          ▼
    Ubuntu server VM

Configure both machines with compatible networking.

On the server:

    sudo apt update
    sudo apt install openssh-server
    sudo systemctl enable --now ssh

Find the server address:

    hostname -I

From the client:

    ssh username@server-ip

After confirming password authentication works, generate a client key:

    ssh-keygen -t ed25519

Copy the public key:

    ssh-copy-id username@server-ip

Reconnect:

    ssh username@server-ip

Inspect the authentication configuration and logs if authentication fails.

This exercise creates a small environment resembling real remote administration.

---

## Linux environment architecture

The concepts in this topic are interconnected.

                    Linux environment
                           │
          ┌────────────────┼────────────────┐
          │                │                │
      Filesystem        Processes        Networking
          │                │                │
     permissions       services            SSH
          │                │                │
       users/groups     systemd        remote access
          │                │                │
          └────────────────┼────────────────┘
                           │
                       Security
                           │
                 authentication
                 authorization
                 least privilege

Virtualization provides the environment in which these concepts can be safely practiced.

---

## Important distinctions

### Terminal versus shell

A terminal is the interface.

A shell interprets commands.

### Linux versus Ubuntu

Linux is the kernel.

Ubuntu is a Linux distribution built around the Linux kernel and a larger collection of software.

### Host versus guest

The host is the physical computer's operating environment.

The guest is the operating system running inside the virtual machine.

### Process versus service

A process is a running program instance.

A service is a managed system component that often runs as a background process.

### SSH client versus SSH server

The client initiates connections.

The server accepts and authenticates connections.

### Private key versus public key

The private key remains secret.

The public key is installed on systems that should accept authentication from the corresponding private key.

### apt versus pip

`apt` manages Ubuntu packages.

`pip` manages Python packages.

### Virtual machine versus container

A virtual machine normally virtualizes a complete operating-system environment.

A container generally shares the host kernel while isolating processes, filesystem views, networking, and resources.

---

## Limitations of virtual-machine-based learning

A VirtualBox Ubuntu environment is valuable but does not perfectly reproduce production infrastructure.

Important differences can include:

- Hardware topology
- Storage performance
- Network architecture
- High availability
- Cloud identity systems
- Distributed storage
- Load balancing
- Monitoring infrastructure
- Disaster recovery
- Multi-node orchestration

The Linux commands and administrative principles remain highly transferable, but production architecture introduces additional layers.

---

## Operational discipline

Good Linux administration depends less on memorizing commands and more on understanding system state.

Before making a change:

    Identify the system
            ↓
    Inspect current state
            ↓
    Determine required change
            ↓
    Assess impact
            ↓
    Apply minimal change
            ↓
    Verify result
            ↓
    Inspect logs if required
            ↓
    Document important configuration

This approach reduces accidental changes and improves troubleshooting.

---

## Final command practice

The following sequence combines several fundamental concepts:

    whoami
    hostname
    pwd
    ls -la
    uname -r
    cat /etc/os-release
    free -h
    df -h
    ip addr
    ip route
    ps aux
    systemctl --failed
    ss -tlnp

For SSH troubleshooting:

    ssh -vvv username@server-ip

For service troubleshooting:

    sudo systemctl status ssh
    sudo journalctl -u ssh --no-pager -n 50

For filesystem troubleshooting:

    pwd
    ls -la
    df -h
    du -sh .

For permission troubleshooting:

    ls -la ~/.ssh
    id
    groups
