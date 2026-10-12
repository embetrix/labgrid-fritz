# labgrid-fritz

Copyright 2026 Embetrix Embedded Systems Solutions <ayoub.zaki@embetrix.com>

Control FRITZ!DECT power sockets from labgrid through an SSH execution host.
The target board, execution host, router and socket are all selected through
configuration. Serial consoles and SD multiplexers are optional, separate resources.

```text
labgrid client --SSH--> lab host --TR-064--> FRITZ!Box --> power socket
```

`FritzPowerDriver` implements `PowerProtocol`: `on`, `off`, `get`, `cycle`, and
reset via power cycling. Commands run on the lab host, where router credentials
remain. A cycle verifies OFF, waits the configured delay, switches ON and verifies
it. Failed OFF verification aborts the cycle.

Tested with labgrid 26.0 and simulated FRITZ! responses; physical hardware
validation is still pending.

## Installation

On the client, using Python 3.11+:

```sh
python -m pip install -e /path/to/labgrid-fritz
```

The execution host needs Python 3.11+, `fritzconnection>=1.15.1,<2`, SSH and rsync.
Labgrid transfers the standalone agent from the client, so installing this plugin
on the host is optional. The `host` extra installs the FRITZ! dependency when
installing the package there: `python -m pip install '.[host]'` from this repository.
Use matching labgrid 26.x releases on the client, exporter and coordinator.

## Host configuration

Copy [examples/fritz.json.example](examples/fritz.json.example) to the execution
host, for example as `/etc/labgrid/fritz.json`. Replace every `YOUR_...` placeholder
with your settings. Each entry under `devices` describes a socket; the resource's
`device` field selects its entry by name. Add entries to configure more sockets,
including sockets on different routers.

Store the router password in the file named by `password_file`. Both paths must
be absolute and readable by the SSH user. Keep the password file private to that
user. On a read-only system, choose a writable persistent directory for these
files and set `config_file` accordingly. Passwords are read only on the execution
host and are never included in exporter resources or client configuration.

The FRITZ!Box must allow TR-064 application access and the configured user must
have permission to control the socket. The transport currently uses HTTP, with
port 49000 as the configurable default.

Merge [examples/exporter.yaml](examples/exporter.yaml) into your exporter config:

```yaml
dut:
  FritzPowerPort:
    host: lab-host
    device: outlet
    config_file: /etc/labgrid/fritz.json
```

`host` names the SSH execution host. `outlet` is an arbitrary key in the JSON
configuration; `dut` is an arbitrary exporter group. Replace them to match your
lab. Release affected places before restarting your exporter, then reacquire
them after it has registered the updated resources.

## Client configuration

Configure SSH access to the execution host without interactive password prompts.
For example, replace the placeholders in this SSH config:

```sshconfig
Host lab-host
    HostName YOUR_LAB_HOST_ADDRESS
    User YOUR_SSH_USER
    UserKnownHostsFile ~/.ssh/known_hosts
    StrictHostKeyChecking yes
```

Verify and record the host key before connecting with labgrid. The remote agent
needs a writable home directory, or set `LG_AGENT_PREFIX` on the client to an
existing writable directory on the host, including a trailing slash.

[examples/target.yaml](examples/target.yaml) is the minimal power-only client
configuration. `imports: [labgrid_fritz]` registers the resource and driver.
Set its `RemotePlace.name` to your place name.

```sh
export LG_COORDINATOR=YOUR_COORDINATOR:20408

# Once, if the place does not exist; replace YOUR_EXPORTER with its actual name:
labgrid-client -p dut create
labgrid-client -p dut add-match 'YOUR_EXPORTER/dut/*'

labgrid-client -c examples/target.yaml -p dut acquire
labgrid-client -c examples/target.yaml -p dut power get
labgrid-client -c examples/target.yaml -p dut power off
labgrid-client -c examples/target.yaml -p dut power on
labgrid-client -c examples/target.yaml -p dut power cycle
labgrid-client -c examples/target.yaml -p dut release
```

The driver's `delay` controls cycle OFF time (default 3 seconds).
`request_timeout` limits each HTTP request; `verify_timeout` limits state polling
apart from an in-flight request. Discovery can involve several HTTP requests.
Connections are reused within an activated driver, not between CLI processes.

## Optional: power, SD mux and serial boot sequence

[examples/boot-exporter.yaml](examples/boot-exporter.yaml) adds a UART and USB SD
mux to the power resource. Replace its hardware identifier placeholders and set
the serial speed for your target. Use the corresponding
[examples/boot-target.yaml](examples/boot-target.yaml) on the client.

```sh
labgrid-client -c examples/boot-target.yaml -p dut acquire
python examples/boot.py --config examples/boot-target.yaml --off-delay 3
# Ctrl-C stops the reader; release the reservation when finished:
labgrid-client -c examples/boot-target.yaml -p dut release
```

The script verifies power OFF, waits, sets and checks mux DUT mode, opens serial,
then powers ON and streams output. Opening serial before power-on captures early
boot messages. It works independently of the target board model or bootloader.
This example is a reader; use `labgrid-client ... console` for interactive input.
An error stops the sequence. Ctrl-C closes the reader, preserving the current
power state and reservation. No images or boot settings are changed.

## Exporter behavior

Labgrid 26.0's stock exporter publishes resource classes without a specialized
export handler as static entries. It can therefore publish `FritzPowerPort`
without installing this package into the exporter service. The client loads the
resource definition through `imports` before expanding `RemotePlace`.

Static `avail: True` means configured; it does not indicate router or socket
health. Driver activation queries the socket, and `power get` reads its state.
Unreachable routers, absent sockets, unknown states and failed verification raise
errors. Device exception messages are sanitized to avoid exposing credentials;
the exception type is retained for diagnosis.

Place acquisition coordinates access to the resource. Direct SSH access can
bypass that coordination. Export each physical socket once and avoid concurrent
control of the same socket through unrelated places or tools.

## Development

```sh
python -m pip install -e '.[host,test]'
python -m pytest
python -m build
```

Tests use simulated devices and real labgrid registration, exporter and agent
interfaces. They never contact a router or switch physical hardware.

References: [labgrid imports](https://labgrid.readthedocs.io/en/v26.0/configuration.html#environment-configuration),
[SSH agent](https://github.com/labgrid-project/labgrid/blob/v26.0/labgrid/util/agentwrapper.py),
[static exporter entries](https://github.com/labgrid-project/labgrid/blob/v26.0/labgrid/remote/exporter.py),
[FritzHomeAutomation](https://fritzconnection.readthedocs.io/en/1.15.1/sources/library_modules.html#fritzhomeautomation).
