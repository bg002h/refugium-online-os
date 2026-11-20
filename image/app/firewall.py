"""The IP and Ethernet rules are submitted in a single nftables transaction."""
import re
import subprocess

from settings import BITCOIN, FILTER, RADIO, RELAY, TOR, WEB

# The QEMU NAT gateway is on-link. Only Tor relay IP traffic uses the default route.
NONPUBLIC = ('0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, '
             '172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.168.0.0/16, '
             '198.18.0.0/15, 198.51.100.0/24, 203.0.113.0/24, 224.0.0.0/4, 240.0.0.0/4')


def rules(interface, online):
    if interface is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,15}', interface):
        raise ValueError('Unexpected uplink name')
    if online and not interface:
        raise ValueError('A network adapter is required')
    ingress = egress = link = ''
    if interface:
        # This VM uses static IPv4. Only the gateway may exchange ARP with it.
        ether_out = ether_in = ''
        if online:
            ether_out = '''ether type arp arp saddr ip 10.0.2.15 arp daddr ip 10.0.2.2 accept
            ether type ip ip protocol tcp tcp dport 443 accept'''
            ether_in = '''ether type arp arp saddr ip 10.0.2.2 arp daddr ip 10.0.2.15 accept
            ether type ip ip protocol tcp tcp sport 443 accept'''
            egress = f'''oifname "{interface}" ip daddr {{ {NONPUBLIC} }} drop
            oifname "{interface}" meta skuid {TOR} tcp dport 443 ct state {{ new, established }} accept'''
            ingress = f'iifname "{interface}" tcp sport 443 ct state established accept'
        link = f'''table netdev gate {{
        chain outbound {{ type filter hook egress device "{interface}" priority 0; policy drop;
            {ether_out}
        }}
        chain inbound {{ type filter hook ingress device "{interface}" priority 0; policy drop;
            {ether_in}
        }}
    }}'''
    local_tor = ''
    if online:
        local_tor = f'''oifname "lo" ip daddr 127.0.0.1 meta skuid {FILTER} tcp dport 9050 accept
            oifname "lo" ip daddr 127.0.0.1 meta skuid {FILTER} tcp dport 9051 accept'''
    return f'''flush ruleset
    table ip firewall {{
        chain input {{ type filter hook input priority 0; policy drop;
            iifname "lo" accept
            {ingress}
        }}
        chain output {{ type filter hook output priority 0; policy drop;
            oifname "lo" ct state established accept
            oifname "lo" ip daddr 127.0.0.1 meta skuid {{ 0, {BITCOIN}, {WEB} }} tcp dport 38332 accept
            oifname "lo" ip daddr 127.0.0.1 meta skuid {{ 0, {RELAY} }} tcp dport {{ 8332, 8432 }} accept
            oifname "lo" ip saddr 127.0.0.1 ip daddr 239.0.0.2 meta skuid {RADIO} udp dport 4434 accept
            {local_tor}
            {egress}
        }}
        chain forward {{ type filter hook forward priority 0; policy drop; }}
    }}
    {link}
'''


def install(interface, online):
    subprocess.run(['/usr/sbin/nft', '-f', '-'], input=rules(interface, online), text=True, check=True)
