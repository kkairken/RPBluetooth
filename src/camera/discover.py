"""
RTSP camera auto-discovery module.
Scans Ethernet subnets for hosts with open RTSP port (554).
Uses only stdlib: socket, subprocess, ipaddress, concurrent.futures.
"""
import ipaddress
import logging
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Ethernet interface prefixes (Linux)
ETHERNET_PREFIXES = ("eth", "end", "enp", "eno", "ens")


def _get_ethernet_subnets() -> List[Tuple[str, ipaddress.IPv4Network, str]]:
    """
    Get Ethernet interfaces and their IPv4 subnets.

    Returns:
        List of (interface_name, network, own_ip) tuples
    """
    result = subprocess.run(
        ["ip", "-4", "-o", "addr", "show"],
        capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        raise RuntimeError(f"'ip addr' failed: {result.stderr.strip()}")

    subnets = []
    for line in result.stdout.strip().splitlines():
        # Format: "2: eth0    inet 192.168.1.10/24 brd 192.168.1.255 scope global eth0"
        parts = line.split()
        if len(parts) < 4:
            continue

        iface = parts[1].rstrip(":")
        # Check if this is an Ethernet interface
        if not any(iface.startswith(prefix) for prefix in ETHERNET_PREFIXES):
            continue

        # Find "inet" and get the address
        try:
            inet_idx = parts.index("inet")
            addr_cidr = parts[inet_idx + 1]  # e.g. "192.168.1.10/24"
        except (ValueError, IndexError):
            continue

        try:
            interface = ipaddress.IPv4Interface(addr_cidr)
            network = interface.network
            own_ip = str(interface.ip)
            subnets.append((iface, network, own_ip))
            logger.debug(f"Found Ethernet interface {iface}: {addr_cidr} (network {network})")
        except (ipaddress.AddressValueError, ValueError) as e:
            logger.debug(f"Skipping invalid address {addr_cidr} on {iface}: {e}")

    return subnets


def _check_port(host: str, port: int, timeout: float) -> Optional[str]:
    """
    Check if a TCP port is open on a host.

    Returns:
        The host IP if port is open, None otherwise
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((host, port))
            return host
    except (socket.timeout, ConnectionRefusedError, OSError):
        return None


def discover_rtsp_camera(
    port: int = 554,
    timeout: float = 0.5,
    max_workers: int = 50
) -> str:
    """
    Discover an RTSP camera on local Ethernet subnets.

    Scans all Ethernet interfaces' subnets for a host with the given port open.
    The camera is expected to be the only device with port 554 open.

    Args:
        port: RTSP port to scan (default 554)
        timeout: TCP connect timeout per host in seconds
        max_workers: Max parallel scan threads

    Returns:
        IP address of the discovered camera

    Raises:
        RuntimeError: If no camera found or no Ethernet interfaces available
    """
    subnets = _get_ethernet_subnets()
    if not subnets:
        raise RuntimeError(
            "No Ethernet interfaces found. "
            "Looked for interfaces starting with: "
            + ", ".join(ETHERNET_PREFIXES)
        )

    # Collect own IPs to skip
    own_ips = {s[2] for s in subnets}

    # Build list of hosts to scan
    hosts_to_scan = []
    for iface, network, own_ip in subnets:
        logger.info(f"Will scan {network} on {iface} for RTSP camera (port {port})")
        for host in network.hosts():
            host_str = str(host)
            if host_str not in own_ips:
                hosts_to_scan.append(host_str)

    if not hosts_to_scan:
        raise RuntimeError("No hosts to scan in Ethernet subnets")

    logger.info(f"Scanning {len(hosts_to_scan)} hosts for RTSP port {port}...")

    # Parallel scan
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_check_port, host, port, timeout): host
            for host in hosts_to_scan
        }
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                # Found a camera — cancel remaining futures
                logger.info(f"RTSP camera discovered at {result}:{port}")
                for f in futures:
                    f.cancel()
                return result

    raise RuntimeError(
        f"No RTSP camera found on port {port}. "
        f"Scanned {len(hosts_to_scan)} hosts on subnets: "
        + ", ".join(f"{s[1]} ({s[0]})" for s in subnets)
    )
