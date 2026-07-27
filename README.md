# modem-conformance-harness
Cellular modem simulator + conformance test harness

## Supported AT commands (simulator — frozen after Day 6)

| Command | Form(s) | What it does |
|---|---|---|
| `AT` | execute | Attention / liveness check -> OK |
| `ATE0` / `ATE1` | basic | Turn command echo off / on |
| `AT+CGMI` | execute | Manufacturer identification |
| `AT+CGMM` | execute | Model identification |
| `AT+CIMI` | execute | IMSI (subscriber id); requires ready SIM |
| `AT+CSQ` | execute | Signal quality (+CSQ: rssi,ber) |
| `AT+CPIN` | read / write | SIM status; write a PIN to unlock |
| `AT+CFUN` | read / write / test | Phone functionality (radio on/off) |
| `AT+CREG` | read / write / test | Network registration status |
| `AT+CGATT` | read / write | Packet-service attach/detach |
| `AT+COPS` | read / write / test | Operator selection / name |
| `AT+CGDCONT` | read / write / test | Define/list PDP (data) contexts |
| `AT+CMEE` | read / write / test | Error-report verbosity (0/1/2) |

All commands follow public 3GPP TS 27.007. Unknown commands and malformed input
return an error (wording depends on the AT+CMEE setting) and never crash the
server.