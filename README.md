# labgrid-fritz

Control FRITZ!DECT sockets with standard `labgrid-client` commands. The proxy
runs on the lab host; router credentials stay there.

`labgrid client → SSH tunnel → labgrid-fritz-proxy → FRITZ!Box → socket`

Requires Python 3.11+, labgrid 26.x, a running coordinator/exporter, and SSH
access from the client to the lab host with key authentication and a verified host
key. Enable TR-064 application access on the FRITZ!Box and allow the lab host
to reach its TCP port 49000.

## 1. Install on the lab host

Skip this step if your image already includes the proxy and service.
Otherwise, run as root from this repository:

```sh
python3 -m venv /opt/labgrid-fritz
/opt/labgrid-fritz/bin/pip install '.[host]'
install -m 0644 examples/labgrid-fritz.service /etc/systemd/system/labgrid-fritz.service
sed -i 's|/usr/bin/labgrid-fritz-proxy|/opt/labgrid-fritz/bin/labgrid-fritz-proxy|' \
  /etc/systemd/system/labgrid-fritz.service
systemctl daemon-reload
```

## 2. Configure the router and password

Create `/etc/labgrid/fritz.json` from [fritz.json.example](examples/fritz.json.example)
and replace the placeholders. Keep the device name `outlet` and:

```json
"password_credential": "fritz-password"
```

Store only the router password in `/etc/labgrid/fritz-password`, then run:

```sh
chmod 0755 /etc/labgrid
chown root:root /etc/labgrid/fritz.json /etc/labgrid/fritz-password
chmod 0644 /etc/labgrid/fritz.json
chmod 0600 /etc/labgrid/fritz-password
systemctl enable --now labgrid-fritz.service
```

The service uses `DynamicUser=yes`; systemd supplies the password using
`LoadCredential=`. Restart `labgrid-fritz` after changing its password.

## 3. Configure the exporter

Merge this resource into the exporter configuration (normally
`/etc/labgrid/configuration.yaml`):

```yaml
dut:
  NetworkPowerPort:
    model: rest
    host: 'http://127.0.0.1:20409/outlets/{index}'
    index: 1
```

Run the exporter with **`--isolated`**. Its advertised hostname must resolve
through the client's SSH configuration; set `--hostname YOUR_SSH_ALIAS` if needed.
Index `1` maps to `outlet` through the service's `--outlet 1=outlet` option.
Release any held place before restarting `labgrid-exporter`.

For upgrades, check the live files: persistent `/etc/labgrid` may retain old
settings. Replace `FritzPowerPort` with the block above and `password_file` with
`password_credential`. Exporter YAML comments must start with `##`.

## 4. Use from the labgrid client

Only standard labgrid is needed on the client; no FRITZ plugin or client YAML.
Replace the coordinator address and exporter name below:

```sh
export LG_COORDINATOR=YOUR_COORDINATOR:20408

# Once, if this place does not exist:
labgrid-client -p dut create
labgrid-client -p dut add-match 'YOUR_EXPORTER/dut/*'

labgrid-client -p dut acquire
labgrid-client -p dut power get
labgrid-client -p dut power off
labgrid-client -p dut power on
labgrid-client -p dut power cycle --delay 3
labgrid-client -p dut release
```

For failures, run `journalctl -u labgrid-fritz -n 50 --no-pager` on the lab host.
Optional serial/SD mux boot setup: [exporter](examples/boot-exporter.yaml),
[client environment](examples/boot-target.yaml), [script](examples/boot.py).
