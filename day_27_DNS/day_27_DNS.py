"""
DNS: Hierarchy, Recursive Resolution, Authoritative Servers, Records, and Caching
================================================================================

A standalone study and executable demonstration of the Domain Name System (DNS).

This script progresses from beginner concepts to advanced resolution behavior:

1. What DNS is and why it exists
2. Names, labels, domains, and fully qualified domain names
3. DNS hierarchy
4. Root, TLD, authoritative, and recursive servers
5. Recursive versus iterative resolution
6. DNS resource records
7. Common record types and their fields
8. TTL and caching
9. Positive and negative caching
10. A simulated recursive resolver
11. Cache expiration
12. Delegation between DNS zones
13. CNAME chains
14. Round-robin A records
15. DNSSEC concepts
16. Security and operational considerations
17. Debugging and diagnostic examples
18. Complexity and performance considerations
19. A realistic end-to-end resolution simulation

The network operations are simulated locally so that the program remains
self-contained and deterministic. No third-party package is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple
import random
import time


# ============================================================================
# 1. FUNDAMENTALS
# ============================================================================

def section(title: str) -> None:
    """Print a readable section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain_dns_basics() -> None:
    section("1. DNS FUNDAMENTALS")

    print(
        """
DNS stands for Domain Name System. It is a distributed naming system used
primarily to map human-readable domain names to network information.

A person can remember:

    www.example.com

more easily than:

    93.184.216.34

DNS separates naming from addressing. A DNS answer can contain many kinds
of information, not just IP addresses.

Important terminology:

- Domain name:
  A hierarchical name such as example.com.
- Hostname:
  A name identifying a host, such as www.example.com.
- Label:
  A component between dots. In www.example.com, the labels are
  www, example, and com.
- FQDN:
  Fully Qualified Domain Name. The DNS root can be represented by a
  trailing dot, so www.example.com. is an absolute DNS name.
- Zone:
  A portion of the DNS namespace administered by an authoritative
  organization.
- Resource record:
  A structured piece of DNS data, such as an A or MX record.
- Resolver:
  A component that obtains DNS answers for clients.
- Authoritative server:
  A server that provides authoritative data for a DNS zone.
"""
    )

    names = [
        "www.example.com",
        "example.com",
        "com",
        ".",
    ]

    for name in names:
        labels = [] if name == "." else name.rstrip(".").split(".")
        print(f"{name:22} -> labels: {labels}")


# ============================================================================
# 2. DNS HIERARCHY
# ============================================================================

def explain_hierarchy() -> None:
    section("2. DNS HIERARCHY")

    print(
        """
DNS is hierarchical.

A simplified namespace looks like this:

    .
    |
    +-- com
    |   |
    |   +-- example
    |       |
    |       +-- www
    |
    +-- org
        |
        +-- example

The root is written as ".".

Under the root are top-level domains (TLDs), such as:
- com
- org
- net
- country-code TLDs such as in, uk, and jp

A registered domain can exist below a TLD:

    example.com

A hostname can exist below that domain:

    www.example.com

The hierarchy enables distributed administration. A single organization
does not need to maintain every DNS record on the Internet.
"""
    )

    hierarchy = {
        ".": ["com", "org", "net", "in"],
        "com": ["example.com", "example.net"],
        "example.com": ["www.example.com", "mail.example.com"],
    }

    for parent, children in hierarchy.items():
        print(f"{parent} -> {', '.join(children)}")


# ============================================================================
# 3. DNS SERVER ROLES
# ============================================================================

class ServerRole(Enum):
    ROOT = "Root"
    TLD = "TLD"
    AUTHORITATIVE = "Authoritative"
    RECURSIVE = "Recursive"


@dataclass
class DNSServer:
    name: str
    role: ServerRole
    zones: List[str] = field(default_factory=list)

    def describe(self) -> str:
        zone_text = ", ".join(self.zones) if self.zones else "none"
        return (
            f"{self.name}: role={self.role.value}, "
            f"zones={zone_text}"
        )


def explain_server_roles() -> None:
    section("3. DNS SERVER ROLES")

    servers = [
        DNSServer("root-server", ServerRole.ROOT, ["."]),
        DNSServer("com-tld-server", ServerRole.TLD, ["com"]),
        DNSServer("example-authoritative", ServerRole.AUTHORITATIVE,
                  ["example.com"]),
        DNSServer("local-recursive", ServerRole.RECURSIVE),
    ]

    for server in servers:
        print(server.describe())

    print(
        """
Root servers:
    Know where authoritative servers for TLDs can be found.

TLD servers:
    Know where authoritative servers for delegated domains can be found.

Authoritative servers:
    Store and publish authoritative records for their zones.

Recursive resolvers:
    Receive a question from a client and perform the lookup process,
    potentially consulting multiple DNS servers and using a cache.

A recursive resolver does not have to be authoritative for the requested
domain. It acts as the client's intermediary.
"""
    )


# ============================================================================
# 4. RESOURCE RECORDS
# ============================================================================

@dataclass(frozen=True)
class DNSRecord:
    name: str
    record_type: str
    value: str
    ttl: int
    priority: Optional[int] = None

    def __str__(self) -> str:
        priority = "" if self.priority is None else f" priority={self.priority}"
        return (
            f"{self.name} {self.ttl} IN {self.record_type} "
            f"{self.value}{priority}"
        )


def explain_record_types() -> None:
    section("4. DNS RESOURCE RECORDS")

    records = [
        DNSRecord("example.com.", "A", "93.184.216.34", 300),
        DNSRecord("example.com.", "AAAA", "2606:2800:220:1:248:1893:25c8:1946", 300),
        DNSRecord("www.example.com.", "CNAME", "example.com.", 600),
        DNSRecord("example.com.", "MX", "mail.example.com.", 3600, priority=10),
        DNSRecord("example.com.", "NS", "ns1.example.com.", 86400),
        DNSRecord("example.com.", "TXT", "v=spf1 -all", 3600),
    ]

    for record in records:
        print(record)

    print(
        """
Important record types:

A
    Maps a name to an IPv4 address.

AAAA
    Maps a name to an IPv6 address.

CNAME
    Creates an alias to another DNS name.

MX
    Identifies mail servers. Lower preference values generally indicate
    higher preference.

NS
    Identifies authoritative name servers for a zone.

TXT
    Stores text associated with a DNS name. It is widely used for
    verification and email-related policies.

SOA
    Contains administrative information about a DNS zone.

PTR
    Used for reverse DNS mappings.

SRV
    Describes services using a target, port, priority, and weight.

CAA
    Specifies which certificate authorities may issue certificates
    for a domain.

DNS records contain:
    owner name + type + class + TTL + record-specific data.

The class used on the public Internet is normally IN, meaning Internet.
"""
    )


# ============================================================================
# 5. NAME NORMALIZATION
# ============================================================================

def normalize_name(name: str) -> str:
    """
    Normalize a DNS name for dictionary lookup.

    DNS names are case-insensitive, so Example.COM and example.com
    represent the same DNS name for normal DNS processing.
    """
    normalized = name.strip().lower()

    if not normalized:
        raise ValueError("DNS name cannot be empty.")

    if not normalized.endswith("."):
        normalized += "."

    return normalized


def validate_dns_name(name: str) -> bool:
    """
    Perform practical validation for ordinary DNS host/domain names.

    This intentionally does not attempt to implement every possible
    internationalized-domain-name rule.
    """
    try:
        normalized = normalize_name(name)
    except ValueError:
        return False

    if normalized == ".":
        return True

    if len(normalized) > 253:
        return False

    labels = normalized.rstrip(".").split(".")

    for label in labels:
        if not 1 <= len(label) <= 63:
            return False

        if label.startswith("-") or label.endswith("-"):
            return False

        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
        if any(character not in allowed for character in label):
            return False

    return True


def demonstrate_name_rules() -> None:
    section("5. DNS NAME VALIDATION AND NORMALIZATION")

    examples = [
        "Example.COM",
        "www.example.com.",
        "mail.example.com",
        "",
        "-invalid.example",
        "valid-name.example",
    ]

    for name in examples:
        print(
            f"{name!r:30} "
            f"valid={validate_dns_name(name)}"
        )

    print(
        """
DNS names are case-insensitive for ordinary DNS comparisons.

For example:

    Example.COM
    example.com
    EXAMPLE.COM

refer to the same DNS name.

A trailing dot indicates an absolute name:

    example.com.

Without the trailing dot, applications may treat a name as relative
depending on the DNS configuration and resolver search rules.
"""
    )


# ============================================================================
# 6. AUTHORITATIVE ZONE
# ============================================================================

@dataclass
class DNSZone:
    origin: str
    records: Dict[Tuple[str, str], List[DNSRecord]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.origin = normalize_name(self.origin)

    def add_record(self, record: DNSRecord) -> None:
        key = (normalize_name(record.name), record.record_type.upper())
        self.records.setdefault(key, []).append(record)

    def query(self, name: str, record_type: str) -> List[DNSRecord]:
        key = (normalize_name(name), record_type.upper())
        return list(self.records.get(key, []))

    def has_name(self, name: str) -> bool:
        normalized = normalize_name(name)
        return any(record_name == normalized for record_name, _ in self.records)


def build_example_zone() -> DNSZone:
    zone = DNSZone("example.com.")

    zone.add_record(DNSRecord(
        "example.com.", "SOA",
        "ns1.example.com. hostmaster.example.com. "
        "2026092701 3600 600 604800 300",
        3600
    ))

    zone.add_record(DNSRecord(
        "example.com.", "NS", "ns1.example.com.", 86400
    ))
    zone.add_record(DNSRecord(
        "example.com.", "NS", "ns2.example.com.", 86400
    ))

    zone.add_record(DNSRecord(
        "example.com.", "A", "93.184.216.34", 300
    ))

    zone.add_record(DNSRecord(
        "example.com.", "AAAA",
        "2606:2800:220:1:248:1893:25c8:1946",
        300
    ))

    zone.add_record(DNSRecord(
        "www.example.com.", "CNAME", "example.com.", 600
    ))

    zone.add_record(DNSRecord(
        "mail.example.com.", "A", "192.0.2.25", 300
    ))

    zone.add_record(DNSRecord(
        "example.com.", "MX", "mail.example.com.", 3600, priority=10
    ))

    zone.add_record(DNSRecord(
        "example.com.", "TXT", "v=spf1 -all", 3600
    ))

    zone.add_record(DNSRecord(
        "api.example.com.", "A", "192.0.2.50", 30
    ))

    return zone


def show_zone(zone: DNSZone) -> None:
    print(f"Authoritative zone: {zone.origin}")

    for records in zone.records.values():
        for record in records:
            print(f"  {record}")


# ============================================================================
# 7. SIMULATED DNS INFRASTRUCTURE
# ============================================================================

@dataclass
class Referral:
    zone: str
    name_servers: List[str]

    def __str__(self) -> str:
        return (
            f"Referral for {self.zone}: "
            f"{', '.join(self.name_servers)}"
        )


@dataclass
class DNSAnswer:
    name: str
    record_type: str
    records: List[DNSRecord]
    authoritative: bool = False
    referral: Optional[Referral] = None
    negative: bool = False

    @property
    def found(self) -> bool:
        return bool(self.records)


class SimulatedDNSNetwork:
    """
    Small in-memory DNS environment.

    It models:
        root -> TLD -> authoritative

    The purpose is educational. Real DNS infrastructure is much larger
    and uses UDP/TCP, message IDs, flags, compression, transport behavior,
    delegation glue, DNSSEC, EDNS, and many operational mechanisms.
    """

    def __init__(self) -> None:
        self.root_servers: Dict[str, DNSServer] = {}
        self.tld_servers: Dict[str, DNSServer] = {}
        self.authoritative_zones: Dict[str, DNSZone] = {}

        self.root_delegations: Dict[str, List[str]] = {
            "com.": ["com-tld-1."]
        }

        self.tld_delegations: Dict[str, List[str]] = {
            "example.com.": [
                "ns1.example.com.",
                "ns2.example.com.",
            ]
        }

        self.zones_by_server: Dict[str, DNSZone] = {}

        self._create_servers()
        self._create_zones()

    def _create_servers(self) -> None:
        self.root_servers["root-1."] = DNSServer(
            "root-1.", ServerRole.ROOT, ["."]
        )

        self.tld_servers["com-tld-1."] = DNSServer(
            "com-tld-1.", ServerRole.TLD, ["com."]
        )

    def _create_zones(self) -> None:
        zone = build_example_zone()

        self.authoritative_zones["example.com."] = zone

        self.zones_by_server["ns1.example.com."] = zone
        self.zones_by_server["ns2.example.com."] = zone

    @staticmethod
    def _is_subdomain(name: str, zone: str) -> bool:
        name = normalize_name(name)
        zone = normalize_name(zone)

        if zone == ".":
            return True

        return name == zone or name.endswith(zone)

    def root_query(self, name: str) -> DNSAnswer:
        labels = normalize_name(name).rstrip(".").split(".")

        if not labels:
            return DNSAnswer(name, "NS", [])

        tld = labels[-1] + "."

        if tld not in self.root_delegations:
            return DNSAnswer(
                name=name,
                record_type="NS",
                records=[],
                authoritative=True,
                negative=True,
            )

        return DNSAnswer(
            name=name,
            record_type="NS",
            records=[],
            referral=Referral(tld, self.root_delegations[tld]),
        )

    def tld_query(self, server_name: str, name: str) -> DNSAnswer:
        normalized_name = normalize_name(name)

        matching_zone = None
        for zone in self.tld_delegations:
            if self._is_subdomain(normalized_name, zone):
                if matching_zone is None or len(zone) > len(matching_zone):
                    matching_zone = zone

        if matching_zone is None:
            return DNSAnswer(
                name=name,
                record_type="NS",
                records=[],
                authoritative=True,
                negative=True,
            )

        return DNSAnswer(
            name=name,
            record_type="NS",
            records=[],
            referral=Referral(
                matching_zone,
                self.tld_delegations[matching_zone]
            ),
        )

    def authoritative_query(
        self,
        server_name: str,
        name: str,
        record_type: str
    ) -> DNSAnswer:
        zone = self.zones_by_server.get(normalize_name(server_name))

        if zone is None:
            return DNSAnswer(
                name=name,
                record_type=record_type,
                records=[],
                negative=True,
            )

        records = zone.query(name, record_type)

        if records:
            return DNSAnswer(
                name=name,
                record_type=record_type,
                records=records,
                authoritative=True,
            )

        # If the exact owner name exists but not the requested type,
        # the simulated result is a NODATA-style negative answer.
        return DNSAnswer(
            name=name,
            record_type=record_type,
            records=[],
            authoritative=True,
            negative=True,
        )


# ============================================================================
# 8. ITERATIVE RESOLUTION
# ============================================================================

def iterative_resolution(
    network: SimulatedDNSNetwork,
    name: str,
    record_type: str
) -> DNSAnswer:
    """
    Demonstrate iterative resolution.

    The caller asks one server at a time:
        root -> TLD -> authoritative

    Each server either answers or refers the caller to another level.
    """
    normalized_name = normalize_name(name)

    print(f"\nIterative lookup: {normalized_name} {record_type}")

    root_answer = network.root_query(normalized_name)
    print(f"  ROOT -> {root_answer.referral}")

    if root_answer.referral is None:
        return root_answer

    tld_server = root_answer.referral.name_servers[0]

    tld_answer = network.tld_query(tld_server, normalized_name)
    print(f"  TLD  -> {tld_answer.referral}")

    if tld_answer.referral is None:
        return tld_answer

    authoritative_server = tld_answer.referral.name_servers[0]

    authoritative_answer = network.authoritative_query(
        authoritative_server,
        normalized_name,
        record_type
    )

    print(
        f"  AUTH -> authoritative={authoritative_answer.authoritative}, "
        f"found={authoritative_answer.found}"
    )

    return authoritative_answer


# ============================================================================
# 9. CACHE
# ============================================================================

@dataclass
class CacheEntry:
    records: List[DNSRecord]
    expires_at: float
    negative: bool = False

    def remaining_ttl(self, now: Optional[float] = None) -> int:
        current_time = time.monotonic() if now is None else now
        return max(0, int(self.expires_at - current_time))

    def is_expired(self, now: Optional[float] = None) -> bool:
        current_time = time.monotonic() if now is None else now
        return current_time >= self.expires_at


class DNSCache:
    """
    A simple TTL-based cache.

    Real resolvers use more sophisticated cache structures and policies,
    but the fundamental rule is the same:

        cache expiration = insertion time + TTL

    Once an entry expires, the resolver must obtain fresh data.
    """

    def __init__(self) -> None:
        self.entries: Dict[Tuple[str, str], CacheEntry] = {}

    def get(
        self,
        name: str,
        record_type: str,
        now: Optional[float] = None
    ) -> Optional[CacheEntry]:
        key = (normalize_name(name), record_type.upper())
        entry = self.entries.get(key)

        if entry is None:
            return None

        if entry.is_expired(now):
            del self.entries[key]
            return None

        return entry

    def put(
        self,
        name: str,
        record_type: str,
        records: Iterable[DNSRecord],
        now: Optional[float] = None,
        negative: bool = False,
        ttl_override: Optional[int] = None
    ) -> None:
        current_time = time.monotonic() if now is None else now
        record_list = list(records)

        if ttl_override is not None:
            ttl = max(0, ttl_override)
        elif record_list:
            ttl = min(record.ttl for record in record_list)
        else:
            # Negative caching uses an explicit TTL in this simulation.
            ttl = 30

        key = (normalize_name(name), record_type.upper())

        self.entries[key] = CacheEntry(
            records=record_list,
            expires_at=current_time + ttl,
            negative=negative,
        )

    def remove_expired(self, now: Optional[float] = None) -> int:
        current_time = time.monotonic() if now is None else now

        expired_keys = [
            key
            for key, entry in self.entries.items()
            if entry.is_expired(current_time)
        ]

        for key in expired_keys:
            del self.entries[key]

        return len(expired_keys)

    def clear(self) -> None:
        self.entries.clear()

    def size(self) -> int:
        return len(self.entries)


# ============================================================================
# 10. RECURSIVE RESOLVER
# ============================================================================

@dataclass
class ResolutionResult:
    name: str
    record_type: str
    records: List[DNSRecord]
    from_cache: bool
    authoritative: bool
    negative: bool
    queries_performed: int


class RecursiveResolver:
    """
    Educational recursive resolver.

    It hides the iterative process from its client.

    Client:
        "Give me www.example.com A"

    Resolver:
        checks cache
        -> root
        -> TLD
        -> authoritative server
        -> follows CNAME if necessary
        -> caches result
        -> returns answer
    """

    def __init__(
        self,
        network: SimulatedDNSNetwork,
        negative_ttl: int = 30
    ) -> None:
        self.network = network
        self.cache = DNSCache()
        self.negative_ttl = negative_ttl
        self.query_count = 0

    def resolve(
        self,
        name: str,
        record_type: str,
        now: Optional[float] = None,
        max_cname_depth: int = 8
    ) -> ResolutionResult:
        normalized_name = normalize_name(name)
        record_type = record_type.upper()

        cache_entry = self.cache.get(normalized_name, record_type, now)

        if cache_entry is not None:
            return ResolutionResult(
                normalized_name,
                record_type,
                cache_entry.records,
                True,
                not cache_entry.negative,
                cache_entry.negative,
                0,
            )

        return self._resolve_uncached(
            normalized_name,
            record_type,
            now,
            max_cname_depth,
            visited=set(),
        )

    def _resolve_uncached(
        self,
        name: str,
        record_type: str,
        now: Optional[float],
        max_cname_depth: int,
        visited: set[str],
    ) -> ResolutionResult:
        if name in visited:
            raise RuntimeError("CNAME loop detected.")

        if len(visited) >= max_cname_depth:
            raise RuntimeError("Maximum CNAME chain depth exceeded.")

        visited.add(name)

        self.query_count += 1

        answer = iterative_resolution(
            self.network,
            name,
            record_type
        )

        if answer.records:
            self.cache.put(
                name,
                record_type,
                answer.records,
                now=now
            )

            return ResolutionResult(
                name,
                record_type,
                answer.records,
                False,
                answer.authoritative,
                False,
                1,
            )

        # Querying A for a CNAME alias requires following the CNAME target.
        if record_type != "CNAME":
            cname_answer = iterative_resolution(
                self.network,
                name,
                "CNAME"
            )

            if cname_answer.records:
                self.cache.put(
                    name,
                    "CNAME",
                    cname_answer.records,
                    now=now
                )

                target = cname_answer.records[0].value

                target_result = self._resolve_uncached(
                    normalize_name(target),
                    record_type,
                    now,
                    max_cname_depth,
                    visited,
                )

                return ResolutionResult(
                    name,
                    record_type,
                    target_result.records,
                    False,
                    target_result.authoritative,
                    False,
                    1 + target_result.queries_performed,
                )

        self.cache.put(
            name,
            record_type,
            [],
            now=now,
            negative=True,
            ttl_override=self.negative_ttl,
        )

        return ResolutionResult(
            name,
            record_type,
            [],
            False,
            answer.authoritative,
            True,
            1,
        )


# ============================================================================
# 11. CACHE DEMONSTRATION
# ============================================================================

def demonstrate_caching(
    network: SimulatedDNSNetwork,
    resolver: RecursiveResolver
) -> None:
    section("6. RECURSIVE RESOLUTION AND CACHING")

    simulated_time = 1_000_000.0

    print("First lookup: cache miss")
    first = resolver.resolve(
        "example.com.",
        "A",
        now=simulated_time
    )

    print(
        f"Answer={first.records}, "
        f"from_cache={first.from_cache}, "
        f"queries={first.queries_performed}"
    )

    print("\nSecond lookup at the same simulated time: cache hit")
    second = resolver.resolve(
        "example.com.",
        "A",
        now=simulated_time + 10
    )

    entry = resolver.cache.get(
        "example.com.",
        "A",
        now=simulated_time + 10
    )

    remaining = entry.remaining_ttl(
        simulated_time + 10
    ) if entry else 0

    print(
        f"Answer={second.records}, "
        f"from_cache={second.from_cache}, "
        f"remaining_ttl={remaining}s"
    )

    print("\nLookup after the 300-second TTL expires")
    third = resolver.resolve(
        "example.com.",
        "A",
        now=simulated_time + 301
    )

    print(
        f"Answer={third.records}, "
        f"from_cache={third.from_cache}, "
        f"queries={third.queries_performed}"
    )

    print(
        """
Caching reduces latency and decreases traffic to authoritative servers.

A TTL is not a guarantee that all users instantly see an update.
Resolvers that already cached an answer may continue using it until
the cached TTL expires.

Short TTL:
    Faster propagation of changes, but potentially more DNS traffic.

Long TTL:
    Better cache efficiency, but changes may remain cached longer.
"""
    )


# ============================================================================
# 12. NEGATIVE CACHING
# ============================================================================

def demonstrate_negative_caching(
    resolver: RecursiveResolver
) -> None:
    section("7. NEGATIVE CACHING")

    simulated_time = 2_000_000.0

    name = "does-not-exist.example.com."

    first = resolver.resolve(
        name,
        "A",
        now=simulated_time
    )

    print(
        f"First query: found={bool(first.records)}, "
        f"negative={first.negative}, "
        f"from_cache={first.from_cache}"
    )

    second = resolver.resolve(
        name,
        "A",
        now=simulated_time + 10
    )

    print(
        f"Second query: found={bool(second.records)}, "
        f"negative={second.negative}, "
        f"from_cache={second.from_cache}"
    )

    third = resolver.resolve(
        name,
        "A",
        now=simulated_time + 31
    )

    print(
        f"After negative TTL: found={bool(third.records)}, "
        f"negative={third.negative}, "
        f"from_cache={third.from_cache}"
    )

    print(
        """
Negative caching prevents repeated requests for names or record types
that are known not to exist.

Two concepts should be distinguished:

NXDOMAIN:
    The queried DNS name does not exist.

NODATA:
    The name exists, but the requested record type is absent.

A complete DNS implementation must distinguish these cases carefully.
This educational simulation represents both through a negative result,
while real DNS responses contain specific response codes and authority
information.
"""
    )


# ============================================================================
# 13. CNAME
# ============================================================================

def demonstrate_cname(
    resolver: RecursiveResolver
) -> None:
    section("8. CNAME RESOLUTION")

    simulated_time = 3_000_000.0

    result = resolver.resolve(
        "www.example.com.",
        "A",
        now=simulated_time
    )

    print("Requested: www.example.com. A")

    for record in result.records:
        print(f"Resolved address: {record.value}")

    cname_entry = resolver.cache.get(
        "www.example.com.",
        "CNAME",
        now=simulated_time
    )

    print(
        f"CNAME cached: "
        f"{cname_entry.records if cname_entry else None}"
    )

    print(
        """
A CNAME does not normally contain an IP address. It points to another
DNS name.

Example:

    www.example.com. CNAME example.com.
    example.com.     A     93.184.216.34

A resolver requesting A for www.example.com may need to follow the
CNAME and then obtain the A record of the target.

CNAME chains can introduce extra queries and latency. Resolver
implementations also protect themselves against loops and excessive
chain depth.
"""
    )


# ============================================================================
# 14. MULTIPLE RECORDS AND LOAD DISTRIBUTION
# ============================================================================

def demonstrate_multiple_records() -> None:
    section("9. MULTIPLE A RECORDS AND ROUND-ROBIN")

    addresses = [
        "192.0.2.10",
        "192.0.2.11",
        "192.0.2.12",
    ]

    print("A records returned for api.example:")
    for address in addresses:
        print(f"  api.example. A {address}")

    shuffled = addresses.copy()
    random.Random(42).shuffle(shuffled)

    print("\nOne simulated response ordering:")
    print("  " + " -> ".join(shuffled))

    print(
        """
Multiple A or AAAA records can be used for basic distribution.

Round-robin DNS is simple, but it is not a complete load-balancing
system. DNS caching means different clients may retain different
answers, and a DNS resolver does not necessarily provide application-
level health information.

For sophisticated traffic management, DNS may be combined with
health checks, anycast, CDNs, load balancers, and application routing.
"""
    )


# ============================================================================
# 15. DELEGATION AND GLUE
# ============================================================================

def explain_delegation() -> None:
    section("10. DELEGATION")

    print(
        """
DNS authority is delegated down the hierarchy.

For example:

    Root
      |
      +-- com
           |
           +-- example.com

The root delegates responsibility for com to TLD servers.

The com zone can delegate example.com to:

    ns1.example.com.
    ns2.example.com.

The parent publishes NS records identifying the child's authoritative
servers.

A special problem occurs when a delegated name server is itself inside
the delegated child zone.

Example:

    example.com. NS ns1.example.com.

To find ns1.example.com's address, a resolver could need information
from example.com itself. This creates a circular dependency.

Glue records solve this bootstrap problem by providing address
information at the parent side when necessary.

Glue is not simply the same thing as an ordinary authoritative record;
its role is to help the resolver reach the delegated name server.
"""
    )


# ============================================================================
# 16. DNSSEC
# ============================================================================

def explain_dnssec() -> None:
    section("11. DNSSEC CONCEPTS")

    print(
        """
DNS by itself does not inherently provide cryptographic authentication
of DNS data.

DNSSEC adds digital signatures to DNS data so that a validating resolver
can verify that the data was signed by the expected DNS zone.

Important DNSSEC concepts:

DNSKEY
    Publishes public key material.

RRSIG
    Contains a digital signature over DNS records.

DS
    Connects a child zone's DNSSEC identity to the parent.

NSEC / NSEC3
    Helps authenticate certain negative answers.

Chain of trust:

    root
      |
      v
    TLD
      |
      v
    child zone

A validating resolver follows this chain to determine whether DNSSEC
signatures validate.

DNSSEC provides data-origin authentication and integrity protection.
It does not encrypt ordinary DNS queries.

DNS over TLS (DoT) and DNS over HTTPS (DoH) address transport privacy
between a client and a DNS resolver. They solve a different problem from
DNSSEC.
"""
    )


# ============================================================================
# 17. SECURITY
# ============================================================================

def explain_security() -> None:
    section("12. DNS SECURITY CONSIDERATIONS")

    print(
        """
DNS-related security issues include:

1. Cache poisoning
   An attacker attempts to cause a resolver to cache false information.

2. DNS spoofing
   A false DNS response is presented as if it were legitimate.

3. DNS amplification
   Misconfigured open resolvers can be abused to amplify traffic
   toward a victim.

4. DDoS against authoritative infrastructure
   Attackers can overwhelm DNS servers with large query volumes.

5. Domain hijacking
   Unauthorized changes to domain registration or DNS management can
   redirect traffic.

6. Dangling records
   A DNS record pointing to a deleted cloud resource can sometimes
   create a subdomain takeover risk.

7. DNS tunneling
   DNS queries and responses can be abused as a covert data channel.

8. Misconfiguration
   Incorrect records can cause outages, mail delivery failures,
   certificate validation failures, or unexpected routing.

Defensive practices include:
- DNSSEC where appropriate
- Strong account authentication and access control
- Registry and DNS-provider protections
- Monitoring authoritative changes
- Restricting recursive service to intended clients
- Rate limiting and DDoS protection
- Removing stale DNS records
- Auditing delegation and NS records
- Carefully managing TTL values
"""
    )


# ============================================================================
# 18. DEBUGGING
# ============================================================================

def explain_debugging(resolver: RecursiveResolver) -> None:
    section("13. DNS DEBUGGING")

    print(
        """
Typical DNS diagnostic questions:

1. Does the name exist?
2. Which record type is being requested?
3. Is the response authoritative?
4. Is a CNAME involved?
5. Is an old cached answer involved?
6. Which resolver is being used?
7. What is the TTL?
8. Are there multiple records?
9. Is DNSSEC validation failing?
10. Is the problem in the client, recursive resolver, delegation,
    authoritative zone, or application?
"""
    )

    for query_name, record_type in [
        ("example.com.", "A"),
        ("www.example.com.", "A"),
        ("mail.example.com.", "A"),
        ("unknown.example.com.", "A"),
    ]:
        result = resolver.resolve(
            query_name,
            record_type,
            now=4_000_000.0
        )

        print(
            f"{query_name:30} "
            f"{record_type:5} "
            f"records={len(result.records):2} "
            f"cache={result.from_cache} "
            f"negative={result.negative}"
        )

    print(
        """
Useful command-line diagnostic tools on typical operating systems
include utilities such as nslookup and dig.

A diagnostic workflow should compare:
    client -> recursive resolver -> authoritative server

If the authoritative server has the correct record but a client sees
an old result, caching is a possible explanation.

If authoritative data itself is incorrect, flushing a client cache does
not solve the underlying problem.
"""
    )


# ============================================================================
# 19. ADVANCED DNS BEHAVIOR
# ============================================================================

def explain_advanced_topics() -> None:
    section("14. ADVANCED DNS TOPICS")

    print(
        """
Recursive versus iterative:

Recursive:
    The server contacted by the client is asked to obtain the final
    answer.

Iterative:
    A server provides the best information it has, often a referral,
    and the requester continues the process.

Authoritative versus cached:

Authoritative:
    The response comes from data for which the server is authoritative.

Cached:
    The response is stored from a previous lookup and is reused until
    its TTL expires.

TTL behavior:

    expiry = cache_time + TTL

The resolver should not normally use an expired cache entry as a normal
fresh answer.

EDNS:
    DNS extensions that allow larger messages and additional capabilities.

UDP and TCP:
    Traditional DNS commonly uses UDP for ordinary queries. TCP is also
    used when required, including some large responses and zone-transfer
    scenarios. Modern DNS deployments can also use encrypted transports.

Anycast:
    Multiple geographically distributed systems can advertise the same
    IP address, allowing traffic to reach a nearby network location.

Split-horizon DNS:
    Different DNS answers may be provided to different client networks,
    often separating internal and external views.

Reverse DNS:
    IP addresses can be mapped back to names using special reverse
    namespaces:
        IPv4 -> in-addr.arpa
        IPv6 -> ip6.arpa

Zone transfers:
    Secondary authoritative servers can obtain zone data from primary
    infrastructure using mechanisms such as AXFR and IXFR.

Wildcards:
    DNS zones can contain wildcard records that may answer queries for
    names that do not have explicit records, subject to DNS wildcard
    rules.

Delegation:
    Authority can be transferred to another administrative boundary
    without moving the entire namespace.
"""
    )


# ============================================================================
# 20. PERFORMANCE
# ============================================================================

def explain_performance() -> None:
    section("15. PERFORMANCE CONSIDERATIONS")

    print(
        """
A cold DNS lookup may require several network exchanges:

    client
      |
      v
    recursive resolver
      |
      v
    root
      |
      v
    TLD
      |
      v
    authoritative

Caching can collapse that path to:

    client -> recursive resolver -> cached answer

Factors affecting DNS latency include:
- Network round-trip time
- Resolver location
- Cache hit ratio
- Number of delegation steps
- CNAME chains
- DNSSEC validation
- Response size
- Retransmissions
- Server load
- Transport protocol
- Packet loss

A useful operational metric is cache hit ratio:

    cache hits / total queries

A higher cache hit ratio generally means fewer upstream lookups, though
the ideal configuration depends on workload and freshness requirements.

Algorithmic complexity of the educational cache:

Dictionary lookup:
    Average O(1)

Insertion:
    Average O(1)

Deletion:
    Average O(1)

The actual network resolution cost is dominated by network operations,
not Python dictionary complexity.
"""
    )


# ============================================================================
# 21. EDGE CASES
# ============================================================================

def demonstrate_edge_cases(
    network: SimulatedDNSNetwork,
    resolver: RecursiveResolver
) -> None:
    section("16. EDGE CASES AND FAILURE CONDITIONS")

    print("1. Case-insensitive lookup")
    result = resolver.resolve(
        "EXAMPLE.COM",
        "a",
        now=5_000_000.0
    )
    print(result.records)

    print("\n2. Missing name")
    missing = resolver.resolve(
        "missing.example.com.",
        "A",
        now=5_000_000.0
    )
    print(
        f"records={missing.records}, "
        f"negative={missing.negative}"
    )

    print("\n3. Invalid name")
    invalid_names = [
        "-bad.example.com",
        "bad-.example.com",
        "",
    ]

    for name in invalid_names:
        print(
            f"{name!r}: "
            f"valid={validate_dns_name(name)}"
        )

    print("\n4. Cache inspection")
    print(f"Cache entries: {resolver.cache.size()}")

    print("\n5. Expired-entry cleanup")
    removed = resolver.cache.remove_expired(
        now=5_000_000.0 + 10_000
    )
    print(f"Removed entries: {removed}")

    print(
        """
Important failure modes in real DNS include:

SERVFAIL:
    The resolver could not successfully complete the query.

REFUSED:
    The server refuses to answer for policy or configuration reasons.

NXDOMAIN:
    The queried name does not exist.

NODATA:
    The name exists, but the requested type has no record.

Timeout:
    No usable response was received within the configured interval.

SERVFAIL should not automatically be interpreted as "the domain does not
exist." That distinction matters for troubleshooting.
"""
    )


# ============================================================================
# 22. REALISTIC END-TO-END CASE
# ============================================================================

def end_to_end_case(
    network: SimulatedDNSNetwork,
    resolver: RecursiveResolver
) -> None:
    section("17. END-TO-END DNS CASE STUDY")

    simulated_time = 6_000_000.0

    print(
        """
Scenario:
A user enters:

    https://www.example.com

The browser needs the server address. The application asks its configured
DNS resolver for an A record.
"""
    )

    print("Step 1: Client asks recursive resolver")
    print("Step 2: Resolver checks cache")

    cache_entry = resolver.cache.get(
        "www.example.com.",
        "A",
        now=simulated_time
    )

    print(
        f"Cache hit: {cache_entry is not None}"
    )

    print("Step 3: Resolver performs resolution if necessary")

    result = resolver.resolve(
        "www.example.com.",
        "A",
        now=simulated_time
    )

    print(
        f"Step 4: Result={result.records}"
    )

    print(
        f"Step 5: Authoritative={result.authoritative}, "
        f"negative={result.negative}, "
        f"from_cache={result.from_cache}"
    )

    print(
        """
Conceptual request path:

    Browser
       |
       | DNS query
       v
    Recursive Resolver
       |
       | cache miss
       v
    Root
       |
       | referral to .com
       v
    .com TLD
       |
       | referral to example.com
       v
    Authoritative Server
       |
       | CNAME www -> example.com
       v
    Authoritative Server
       |
       | A = 93.184.216.34
       v
    Recursive Resolver
       |
       | cache according to TTL
       v
    Browser

The next client request can often terminate at the recursive resolver
because the answer is cached.
"""
    )


# ============================================================================
# 23. PRACTICAL DESIGN CHECKLIST
# ============================================================================

def print_design_checklist() -> None:
    section("18. DNS DESIGN CHECKLIST")

    checklist = [
        "Define authoritative zones and delegation boundaries.",
        "Use redundant authoritative servers.",
        "Keep NS records consistent.",
        "Choose TTL values based on change frequency and operational needs.",
        "Monitor DNS changes.",
        "Protect DNS management accounts.",
        "Remove stale records.",
        "Avoid unnecessary CNAME chains.",
        "Use IPv6 records when IPv6 service is intentionally supported.",
        "Use DNSSEC where the deployment requires authenticated DNS data.",
        "Restrict recursive DNS service to intended clients.",
        "Plan for DDoS resilience.",
        "Test positive and negative responses.",
        "Test DNS changes from multiple recursive resolvers.",
        "Document dependencies between DNS and application infrastructure.",
    ]

    for number, item in enumerate(checklist, start=1):
        print(f"{number:2}. {item}")


# ============================================================================
# 24. MINI QUIZ
# ============================================================================

def knowledge_check() -> None:
    section("19. KNOWLEDGE CHECK")

    questions = [
        (
            "Which DNS layer is at the top of the hierarchy?",
            "The root."
        ),
        (
            "What does an A record normally contain?",
            "An IPv4 address."
        ),
        (
            "What does an AAAA record normally contain?",
            "An IPv6 address."
        ),
        (
            "What is the purpose of a CNAME?",
            "It aliases one DNS name to another DNS name."
        ),
        (
            "What does TTL control in a cache?",
            "How long cached data may be retained before expiration."
        ),
        (
            "Which server provides authoritative data for a zone?",
            "An authoritative DNS server."
        ),
        (
            "What is a recursive resolver?",
            "A resolver that obtains the requested answer on behalf of its client."
        ),
        (
            "What does DNSSEC provide?",
            "Cryptographic authentication and integrity for DNS data."
        ),
        (
            "Does DNSSEC encrypt ordinary DNS queries?",
            "No."
        ),
        (
            "What happens after a cached answer expires?",
            "The resolver must obtain fresh information before returning a normal fresh answer."
        ),
    ]

    for number, (question, answer) in enumerate(questions, start=1):
        print(f"\n{number}. {question}")
        print(f"   Answer: {answer}")


# ============================================================================
# 25. MAIN PROGRAM
# ============================================================================

def main() -> None:
    print(
        """
##############################################################################
#                                                                            #
#       DNS STUDY LAB                                                        #
#       Hierarchy | Recursive Resolution | Authority | Records | Caching     #
#                                                                            #
##############################################################################
"""
    )

    explain_dns_basics()
    explain_hierarchy()
    explain_server_roles()
    explain_record_types()
    demonstrate_name_rules()

    network = SimulatedDNSNetwork()

    section("AUTHORITATIVE ZONE DATA")
    show_zone(network.authoritative_zones["example.com."])

    resolver = RecursiveResolver(
        network,
        negative_ttl=30
    )

    demonstrate_caching(network, resolver)
    demonstrate_negative_caching(resolver)
    demonstrate_cname(resolver)
    demonstrate_multiple_records()
    explain_delegation()
    explain_dnssec()
    explain_security()
    explain_debugging(resolver)
    explain_advanced_topics()
    explain_performance()
    demonstrate_edge_cases(network, resolver)
    end_to_end_case(network, resolver)
    print_design_checklist()
    knowledge_check()

    section("FINAL DNS TERMINOLOGY MAP")

    terminology = {
        "Root": "Top of the DNS hierarchy.",
        "TLD": "Top-level domain such as com or org.",
        "Zone": "Administratively managed portion of DNS namespace.",
        "Resolver": "Component that obtains DNS answers.",
        "Recursive": "Obtains the final answer on behalf of a client.",
        "Iterative": "Uses referrals and follows the hierarchy step by step.",
        "Authoritative": "Server that serves authoritative zone data.",
        "Record": "Structured DNS information such as A, MX, NS, or TXT.",
        "TTL": "Maximum cache lifetime for an ordinary cached answer.",
        "CNAME": "Alias from one DNS name to another.",
        "DNSSEC": "Cryptographic authentication and integrity for DNS data.",
    }

    for term, meaning in terminology.items():
        print(f"{term:15} -> {meaning}")

    print(
        """
The central relationship to remember is:

    DNS hierarchy
        determines where authority is delegated

    Recursive resolution
        follows that hierarchy on behalf of clients

    Authoritative servers
        publish the source data for their zones

    Resource records
        carry the actual DNS information

    TTL-based caching
        reduces repeated resolution work while preserving a bounded
        period of data reuse
"""
    )


if __name__ == "__main__":
    main()
