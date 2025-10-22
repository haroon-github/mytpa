---
description: How TPA configures and secures etcd.
---

# etcd

`etcd` is a distributed, reliable key-value store commonly used for distributed
coordination. TPA configures `etcd` primarily as the Distributed Configuration
Store (DCS) when using Patroni as the failover manager for PostgreSQL clusters.

TPA automatically deploys and configures a 3-node `etcd` cluster by default when
you enable Patroni in the M1 architecture.

## Installation

TPA installs the `etcd` package available from the configured system
repositories. On SLES and RHEL-based systems, TPA automatically enables the PGDG
`extras` repository to provide the `etcd` package.

## Configuration

TPA generates the `/etc/etcd/etcd.conf` file based on your `config.yml` settings
and cluster topology. It configures peer and client communication URLs, data
directory, and SSL certificates.

## Security

TPA provides robust options for securing communication with and within the
`etcd` cluster. This is controlled primarily by the `etcd_ssl_enabled` and
`etcd_authentication_mode` variables.

### TLS Encryption

Setting `etcd_ssl_enabled: true` enables TLS encryption for all `etcd` traffic.
TPA will automatically:

* Generate a Cluster CA and server certificates (including appropriate IP and
  DNS Subject Alternative Names) for each etcd node.
* Configure etcd to use HTTPS for both peer-to-peer and client-server
  communication.
* Configure clients (`etcdctl`, Patroni) to connect via HTTPS and validate the
  server certificate using the CA.

### Client Authentication

Once TLS encryption is enabled (`etcd_ssl_enabled: true`), you can choose an
authentication mode using the `etcd_authentication_mode` variable:

* **`none` (default):** No client authentication is performed. Communication
  relies solely on TLS encryption if `etcd_ssl_enabled` is `true`.
* **`basic`:** Requires clients to authenticate using a username and password.
  TPA automatically:

  * Creates an administrative `root` user with a generated password.
  * If using Patroni, creates a dedicated, least-privilege user for Patroni
    (configurable via `patroni_etcd_user`) with `readwrite` access only to its
    specific key prefix (e.g., `/tpa/cluster_name`).
  * Configures Patroni to use these dedicated credentials.
* **`mtls`:** Requires clients (including peer nodes) to present a valid TLS
  certificate signed by the trusted cluster CA. TPA automatically:

  * Configures `etcd` to require and validate client certificates for both peer
    (`ETCD_PEER_CLIENT_CERT_AUTH=true`) and client
    (`ETCD_CLIENT_CERT_AUTH=true`) connections.
  * Configures clients (`etcdctl`, Patroni) to present their client certificates
    for authentication.

!!! Note
TPA includes robust logic to handle transitions between different
authentication modes during deployment or reconfiguration, ensuring the
cluster remains stable. Configuration validation checks are performed early to
prevent invalid combinations (e.g., `mtls` requires `etcd_ssl_enabled: true`).
However, it's currently not able to handle transition of values for
`etcd_ssl_enabled` (i.e. from `false` to `true` or vice-versa).
!!!

## Configuration Variables

You can set the following variables for `etcd`.

| Variable | Default value | Description |
| ----- | ----- | ----- |
| `etcd_peer_port` | `2380` | The TCP port `etcd` uses for peer-to-peer (server-to-server) communication. |
| `etcd_client_port` | `2379` | The TCP port `etcd` uses for client communication. |
| `etcd_ssl_enabled` | `false`\* | Enable SSL/TLS encryption for all `etcd` communication. See Security. \* `true` for new clusters via `tpaexec configure`. |
| `etcd_authentication_mode` | `none`\* | Defines the client authentication mode (`none`, `basic`, `mtls`). Requires `etcd_ssl_enabled: true` for modes other than `none`. See Security. \* `mtls` for new clusters via `tpaexec configure`. |
| `etcd_compaction_mode` | `revision` | The automatic compaction mode (`revision` or `periodic`). |
| `etcd_compaction_retention` | `10` | The retention value for automatic compaction. For `revision` mode, this is the number of revisions to keep. For `periodic` mode, this is the time interval (e.g., `1h`). |
