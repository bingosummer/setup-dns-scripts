#!/usr/bin/env python
import os
import sys
import json
from subprocess import call

if len(sys.argv) != 3:
    print "Usage: python setup_dns.py <domain-name> <cf-internal-ip>\n"
    sys.exit(0)
domain_name = sys.argv[1]
cf_internal_ip = sys.argv[2]
domain_name_prefix = domain_name.split('.')[0]
zone_name = '.'.join(domain_name.split('.')[1:])
print "Will setup a DNS server for the domain {0}".format(domain_name)

HOME = os.environ['HOME']
DNS_DIR = '/etc/bind/'
DNS_CONF_FILE = 'named.conf'
DNS_CONF = """// This is the primary configuration file for the BIND DNS server named.
//
// Please read /usr/share/doc/bind9/README.Debian.gz for information on the
// structure of BIND configuration files in Debian, *BEFORE* you customize
// this configuration file.
//
// If you are just adding zones, please do that in /etc/bind/named.conf.local

include "/etc/bind/named.conf.options";
include "/etc/bind/named.conf.local";
view "internal" {{
  match-clients {{ 10.0.0.0/8; }};
  allow-query {{ 10.0.0.0/8; }};
  recursion yes;
  zone "{0}" IN {{
    type master;
    file "{1}{2}";
  }};
  include "{1}named.conf.default-zones";
}};
view "external" {{
  match-clients {{ any; }};
  allow-query {{ any; }};
  recursion no;
  zone "{0}" IN {{
    type master;
    file "{1}{3}";
  }};
  include "{1}named.conf.default-zones";
}};
"""
DNS_CONF_OPT_FILE = 'named.conf.options'
DNS_CONF_OPT = """options {{
        directory "/var/cache/bind";

        // If there is a firewall between you and nameservers you want
        // to talk to, you may need to fix the firewall to allow multiple
        // ports to talk.  See http://www.kb.cert.org/vuls/id/800113

        // If your ISP provided one or more IP addresses for stable
        // nameservers, you probably want to use them as forwarders.
        // Uncomment the following block, and insert the addresses replacing
        // the all-0's placeholder.

        // forwarders {{
        //      0.0.0.0;
        // }};

        //========================================================================
        // If BIND logs error messages about the root key being expired,
        // you will need to update your keys.  See https://www.isc.org/bind-keys
        //========================================================================
        dnssec-validation auto;

        auth-nxdomain no;    # conform to RFC1035
        listen-on {{ any; }};
        forwarders {{
                {0}
        }};
}};
"""
LAN_ZONE_FILE = 'cf.com.lan'
WAN_ZONE_FILE = 'cf.com.wan'
ZONE_CONF = """;
; BIND data file for local loopback interface
;
$TTL    604800
$ORIGIN {2}.
@       IN      SOA     ns      root (
                              1         ; Serial
                         604800         ; Refresh
                          86400         ; Retry
                        2419200         ; Expire
                         604800 )       ; Negative Cache TTL
;
@       IN      NS      ns.{2}.
{2}.        IN      A       {0}
ns      IN      A       {0}
{3}      IN      A       {1}
*.{3}    IN      A       {1}
"""

# Get the namerserver IPs to forward
with open('/etc/resolv.conf', 'r') as tmpfile:
    lines = tmpfile.readlines()
nameserver_ips = [line.strip().split()[-1] for line in lines if line.startswith('nameserver')]
if not nameserver_ips:
    nameserver_ips = ['8.8.8.8', '8.8.4.4']
nameserver_ips = ';'.join(nameserver_ips) + ';'

# Get the reserved IP for CloudFoundry and DNS server
with open(os.path.join(HOME, 'settings'), "r") as tmpfile:
    contents = tmpfile.read()
settings = json.loads(contents)
dns_reserved_ip = settings.get('dns-ip')
cf_reserved_ip = settings.get('cf-ip')
if dns_reserved_ip is None or cf_reserved_ip is None:
    print ("Can't find the reserved IP for CloudFoundry "
           "or DNS server in {0}, exit.").format(os.path.join(HOME, 'settings'))
    sys.exit(0)

# Install bind9
call('apt-get -qq update', shell=True)
call('apt-get install -yqq bind9 bind9utils', shell=True)

dns_conf = DNS_CONF.format(zone_name, DNS_DIR, LAN_ZONE_FILE, WAN_ZONE_FILE)
with open(os.path.join(DNS_DIR, DNS_CONF_FILE), 'w') as f:
    f.write(dns_conf)

dns_conf_opt = DNS_CONF_OPT.format(nameserver_ips)
with open(os.path.join(DNS_DIR, DNS_CONF_OPT_FILE), 'w') as f:
    f.write(dns_conf_opt)

call("ifconfig eth0 | sed -n '/inet addr/p' | awk -F'[: ]+' '{print $4}' > /tmp/dns-internal-ip", shell=True)
with open('/tmp/dns-internal-ip', 'r') as f:
    dns_internal_ip = f.read().strip()
lan_zone_conf = ZONE_CONF.format(dns_internal_ip, cf_internal_ip, zone_name, domain_name_prefix)
with open(os.path.join(DNS_DIR, LAN_ZONE_FILE), 'w') as f:
    f.write(lan_zone_conf)
wan_zone_conf = ZONE_CONF.format(dns_reserved_ip, cf_reserved_ip, zone_name, domain_name_prefix)
with open(os.path.join(DNS_DIR, WAN_ZONE_FILE), 'w') as f:
    f.write(wan_zone_conf)

# Restart bind9
call('/etc/init.d/bind9 restart', shell=True)
sys.exit(0)

