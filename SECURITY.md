# Security

## Reporting

Report vulnerabilities privately through GitHub's security advisories on this
repository, or by email to the address on the author's profile. Please do not open a
public issue for anything exploitable. You will get an acknowledgment within a few
days and a fix or a plan before any public disclosure.

## What this library does and does not do

The runtime makes outbound HTTP requests only to the base URL you configure on your
own transport, using credentials you supply. It stores nothing, sends no telemetry,
and reads nothing beyond the capsule files. Capsules are data, and the bundled corpus
is reviewed with every change, but a capsule you load from your own directory runs
with whatever requests it declares, so treat third-party capsule files like code.

A wrong probe answer is a security-relevant bug here, because callers act on it with
money and data. Misreadings qualify for private reporting too.

## Supported versions

The latest released 0.1.x line receives fixes.
