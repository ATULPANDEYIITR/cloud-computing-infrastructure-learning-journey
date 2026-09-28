"""
HTTP AND HTTPS: A COMPLETE STUDY PROGRAM

This executable study file progresses from HTTP fundamentals to HTTPS, TLS,
certificates, request/response mechanics, security properties, validation,
caching, cookies, redirects, authentication concepts, and practical diagnostics.

The demonstrations intentionally use the Python standard library wherever
possible. Network demonstrations use public HTTPS endpoints only when the
runtime has network access. Most teaching examples are simulated locally so
the file remains useful without network connectivity.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import re
import socket
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from http import HTTPStatus
from typing import Dict, Iterable, List, Mapping, Optional, Tuple


# ============================================================================
# 1. FUNDAMENTAL TERMINOLOGY
# ============================================================================

def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain_http_terms() -> None:
    section("1. HTTP FUNDAMENTALS")

    terms = {
        "HTTP": "Hypertext Transfer Protocol, an application-layer protocol for exchanging messages.",
        "HTTPS": "HTTP carried through a TLS-protected connection.",
        "Client": "The program that initiates a request, such as a browser or API client.",
        "Server": "The program that receives requests and produces responses.",
        "Request": "A client-to-server HTTP message containing a method, target, headers, and optionally a body.",
        "Response": "A server-to-client HTTP message containing a status, headers, and optionally a body.",
        "Header": "Metadata describing a request or response.",
        "Body": "Optional application data transported by the HTTP message.",
        "URI": "A resource identifier. A URL is a commonly used URI containing a retrieval location.",
        "TLS": "Transport Layer Security, the cryptographic protocol used by modern HTTPS.",
        "Certificate": "A digitally signed credential binding a domain identity to a public key.",
    }

    for name, definition in terms.items():
        print(f"{name:12} : {definition}")


# ============================================================================
# 2. HTTP REQUEST STRUCTURE
# ============================================================================

@dataclass
class HttpRequest:
    method: str
    target: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def serialize(self) -> bytes:
        request_line = f"{self.method} {self.target} HTTP/1.1\r\n"
        header_text = "".join(f"{name}: {value}\r\n" for name, value in self.headers.items())
        return (
            request_line.encode("ascii")
            + header_text.encode("iso-8859-1")
            + b"\r\n"
            + self.body
        )

    def display(self) -> None:
        print(self.serialize().decode("iso-8859-1", errors="replace"))


@dataclass
class HttpResponse:
    status_code: int
    reason: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    @property
    def status_class(self) -> str:
        if 100 <= self.status_code <= 199:
            return "1xx Informational"
        if 200 <= self.status_code <= 299:
            return "2xx Successful"
        if 300 <= self.status_code <= 399:
            return "3xx Redirection"
        if 400 <= self.status_code <= 499:
            return "4xx Client Error"
        if 500 <= self.status_code <= 599:
            return "5xx Server Error"
        return "Unknown"


def demonstrate_raw_messages() -> None:
    section("2. HTTP REQUEST AND RESPONSE STRUCTURE")

    request = HttpRequest(
        method="GET",
        target="/api/products?page=1&limit=10",
        headers={
            "Host": "example.test",
            "Accept": "application/json",
            "User-Agent": "HTTPStudyClient/1.0",
            "Connection": "close",
        },
    )

    print("Example HTTP request:")
    request.display()

    response = HttpResponse(
        status_code=200,
        reason="OK",
        headers={
            "Content-Type": "application/json",
            "Content-Length": "42",
            "Cache-Control": "no-cache",
        },
        body=b'{"message":"request processed","items":[]}',
    )

    print("Example HTTP response:")
    print(f"HTTP/1.1 {response.status_code} {response.reason}")
    for key, value in response.headers.items():
        print(f"{key}: {value}")
    print()
    print(response.body.decode())
    print("Classification:", response.status_class)


# ============================================================================
# 3. HTTP METHODS
# ============================================================================

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "PUT", "DELETE", "TRACE"}
COMMON_METHODS = {
    "GET": "Retrieve a representation.",
    "HEAD": "Retrieve headers without the response body.",
    "POST": "Submit data, commonly causing creation or processing.",
    "PUT": "Create or completely replace a resource at a known target.",
    "PATCH": "Partially modify a resource.",
    "DELETE": "Request removal of a resource.",
    "OPTIONS": "Ask what communication options are available.",
    "CONNECT": "Establish a tunnel, commonly through a proxy.",
    "TRACE": "Diagnostic loop-back method; frequently disabled for security reasons.",
}


def demonstrate_methods() -> None:
    section("3. HTTP METHODS")

    for method, purpose in COMMON_METHODS.items():
        safe = "safe" if method in SAFE_METHODS else "not defined as safe"
        idempotent = "idempotent" if method in IDEMPOTENT_METHODS else "not generally idempotent"
        print(f"{method:8} | {safe:24} | {idempotent:29} | {purpose}")

    print("\nExample API operations:")
    operations = [
        ("GET", "/users/42", "Read user 42"),
        ("POST", "/users", "Create a user"),
        ("PUT", "/users/42", "Replace user 42"),
        ("PATCH", "/users/42", "Change selected fields"),
        ("DELETE", "/users/42", "Delete user 42"),
    ]

    for method, target, description in operations:
        print(f"{method:7} {target:15} -> {description}")


# ============================================================================
# 4. STATUS CODES
# ============================================================================

STATUS_GROUPS = {
    "1xx": [100, 101, 102],
    "2xx": [200, 201, 202, 204, 206],
    "3xx": [301, 302, 303, 304, 307, 308],
    "4xx": [400, 401, 403, 404, 405, 408, 409, 410, 412, 413, 415, 422, 429],
    "5xx": [500, 501, 502, 503, 504, 505, 507, 511],
}


def demonstrate_status_codes() -> None:
    section("4. HTTP STATUS CODES")

    for group, codes in STATUS_GROUPS.items():
        print(f"\n{group}")
        for code in codes:
            try:
                phrase = HTTPStatus(code).phrase
            except ValueError:
                phrase = "Unknown"
            print(f"  {code}: {phrase}")

    print("\nImportant distinctions:")
    print("401 means authentication credentials are missing or invalid.")
    print("403 means the server understood the request but refuses authorization.")
    print("404 means the requested resource was not found.")
    print("429 commonly indicates rate limiting.")
    print("502 indicates a gateway/proxy received an invalid upstream response.")
    print("503 commonly indicates temporary service unavailability.")
    print("504 commonly indicates an upstream timeout.")


# ============================================================================
# 5. HEADERS
# ============================================================================

REQUEST_HEADER_PURPOSES = {
    "Host": "Identifies the target host.",
    "Accept": "States response media types the client can process.",
    "Content-Type": "Describes the media type of the message body.",
    "Content-Length": "Specifies body size in bytes when applicable.",
    "Authorization": "Carries authentication credentials or an access token.",
    "User-Agent": "Identifies the client software.",
    "Referer": "Indicates the referring URL when supplied by the client.",
    "Origin": "Identifies the origin associated with a request.",
}

RESPONSE_HEADER_PURPOSES = {
    "Cache-Control": "Controls caching behavior.",
    "ETag": "Provides a representation validator.",
    "Last-Modified": "Communicates a representation modification time.",
    "Location": "Identifies another resource, often for redirects.",
    "Set-Cookie": "Asks the client to store a cookie.",
    "Content-Encoding": "Describes content compression such as gzip.",
    "Strict-Transport-Security": "Instructs supporting browsers to use HTTPS for a period.",
    "Content-Security-Policy": "Restricts browser resource and execution behavior.",
}


def demonstrate_headers() -> None:
    section("5. HTTP HEADERS")

    print("Common request headers:")
    for name, purpose in REQUEST_HEADER_PURPOSES.items():
        print(f"  {name:22} {purpose}")

    print("\nCommon response headers:")
    for name, purpose in RESPONSE_HEADER_PURPOSES.items():
        print(f"  {name:28} {purpose}")

    print("\nHeader names are case-insensitive in HTTP.")
    sample = {"content-type": "application/json", "CONTENT-LENGTH": "18"}
    normalized = {key.lower(): value for key, value in sample.items()}
    print("Normalized representation:", normalized)


# ============================================================================
# 6. URL / URI COMPONENTS
# ============================================================================

def demonstrate_url_structure() -> None:
    section("6. URL STRUCTURE")

    url = "https://api.example.com:8443/v1/users/42?active=true&sort=name#profile"
    parsed = urllib.parse.urlparse(url)

    print("URL:", url)
    print("Scheme:", parsed.scheme)
    print("Hostname:", parsed.hostname)
    print("Port:", parsed.port)
    print("Path:", parsed.path)
    print("Query:", parsed.query)
    print("Fragment:", parsed.fragment)

    query = urllib.parse.parse_qs(parsed.query)
    print("Decoded query:", query)

    encoded = urllib.parse.quote("Alice & Bob / Engineering")
    print("URL-encoded value:", encoded)


# ============================================================================
# 7. HTTP MESSAGE BODY AND CONTENT TYPES
# ============================================================================

def demonstrate_bodies() -> None:
    section("7. MESSAGE BODIES AND CONTENT TYPES")

    user = {
        "name": "Atul",
        "skills": ["Python", "JavaScript", "C++"],
        "active": True,
    }

    json_body = json.dumps(user).encode("utf-8")

    request = HttpRequest(
        method="POST",
        target="/api/users",
        headers={
            "Host": "example.test",
            "Content-Type": "application/json",
            "Content-Length": str(len(json_body)),
        },
        body=json_body,
    )

    request.display()

    print("JSON body bytes:", len(json_body))
    print("Decoded JSON:", json.loads(json_body.decode("utf-8")))

    form = urllib.parse.urlencode({"username": "alice", "role": "admin"})
    print("application/x-www-form-urlencoded:", form)


# ============================================================================
# 8. COOKIES
# ============================================================================

def demonstrate_cookies() -> None:
    section("8. COOKIES")

    set_cookie = (
        "session_id=abc123; Path=/; Secure; HttpOnly; SameSite=Lax"
    )

    print("Set-Cookie:", set_cookie)
    print("Secure: send cookie over HTTPS connections.")
    print("HttpOnly: prevent normal JavaScript access to the cookie.")
    print("SameSite: controls cross-site cookie transmission.")

    cookie_header = "session_id=abc123; theme=dark"
    cookies = {}

    for item in cookie_header.split(";"):
        if "=" in item:
            key, value = item.strip().split("=", 1)
            cookies[key] = value

    print("Parsed request cookies:", cookies)


# ============================================================================
# 9. CACHING AND CONDITIONAL REQUESTS
# ============================================================================

def demonstrate_caching() -> None:
    section("9. CACHING AND CONDITIONAL REQUESTS")

    original_response = {
        "status": 200,
        "ETag": '"product-42-v7"',
        "Cache-Control": "max-age=60",
        "body": '{"id":42,"name":"Keyboard"}',
    }

    print("Initial response:")
    for key, value in original_response.items():
        print(f"  {key}: {value}")

    conditional_request = {
        "If-None-Match": original_response["ETag"]
    }

    print("\nConditional request:", conditional_request)
    print("If representation is unchanged, server can return 304 Not Modified.")
    print("A 304 response normally avoids retransmitting the unchanged body.")


# ============================================================================
# 10. CONTENT NEGOTIATION
# ============================================================================

def choose_media_type(accept_header: str, supported: Iterable[str]) -> Optional[str]:
    supported_set = set(supported)
    candidates = []

    for raw in accept_header.split(","):
        parts = [part.strip() for part in raw.split(";")]
        media_type = parts[0]
        quality = 1.0

        for parameter in parts[1:]:
            if parameter.startswith("q="):
                try:
                    quality = float(parameter[2:])
                except ValueError:
                    quality = 0.0

        candidates.append((quality, media_type))

    candidates.sort(reverse=True)

    for _, requested in candidates:
        if requested in supported_set:
            return requested
        if requested == "*/*":
            return next(iter(supported_set), None)
        if requested.endswith("/*"):
            prefix = requested.split("/", 1)[0]
            for media_type in supported_set:
                if media_type.startswith(prefix + "/"):
                    return media_type

    return None


def demonstrate_content_negotiation() -> None:
    section("10. CONTENT NEGOTIATION")

    accept = "application/json;q=1.0, text/html;q=0.8, */*;q=0.1"
    supported = ["text/html", "application/json"]

    print("Accept:", accept)
    print("Supported:", supported)
    print("Selected:", choose_media_type(accept, supported))


# ============================================================================
# 11. REDIRECTS
# ============================================================================

def demonstrate_redirects() -> None:
    section("11. REDIRECTS")

    redirects = {
        301: "Permanent redirect; clients may update stored references.",
        302: "Found; historically ambiguous, commonly used as a temporary redirect.",
        303: "See Other; commonly redirects after POST to a retrieval URL.",
        307: "Temporary redirect while preserving the HTTP method.",
        308: "Permanent redirect while preserving the HTTP method.",
    }

    for code, description in redirects.items():
        print(f"{code}: {description}")

    print("\nImportant distinction:")
    print("301/302 may cause clients to change POST handling depending on client behavior.")
    print("307/308 explicitly preserve the request method and body semantics.")


# ============================================================================
# 12. HTTP SECURITY PROBLEMS
# ============================================================================

def demonstrate_http_security() -> None:
    section("12. WHY PLAIN HTTP IS NOT SUFFICIENT FOR SENSITIVE DATA")

    threats = [
        ("Eavesdropping", "An attacker able to observe traffic can read unencrypted content."),
        ("Tampering", "An attacker may modify messages when integrity protection is absent."),
        ("Impersonation", "A client has no cryptographic proof that it is communicating with the intended server."),
        ("Session theft", "Unprotected session cookies can be exposed on an untrusted network."),
        ("Downgrade attacks", "Weak protocol negotiation can potentially reduce security if defenses are absent."),
    ]

    for name, explanation in threats:
        print(f"{name:20}: {explanation}")

    print("\nHTTPS addresses these properties through TLS, certificate validation,")
    print("authenticated key exchange, encryption, and integrity protection.")


# ============================================================================
# 13. TLS CONCEPTS
# ============================================================================

def demonstrate_tls_concepts() -> None:
    section("13. TLS CONCEPTS")

    concepts = [
        ("Confidentiality", "Encrypted application data is difficult for network observers to read."),
        ("Integrity", "Authenticated encryption detects unauthorized modification."),
        ("Authentication", "Certificates allow clients to authenticate server identities."),
        ("Public key cryptography", "Used heavily during authentication and key establishment."),
        ("Symmetric cryptography", "Used for efficient bulk application-data encryption."),
        ("Handshake", "Negotiates parameters and establishes protected session keys."),
        ("Certificate chain", "Connects an end-entity certificate to a trusted root authority."),
        ("SNI", "Allows a client to indicate the intended hostname during TLS setup."),
        ("ALPN", "Negotiates application protocols such as HTTP/1.1 or HTTP/2."),
    ]

    for name, definition in concepts:
        print(f"{name:24}: {definition}")


# ============================================================================
# 14. CERTIFICATE INSPECTION
# ============================================================================

def inspect_certificate(hostname: str, port: int = 443, timeout: float = 5.0) -> None:
    section(f"14. TLS CERTIFICATE INSPECTION: {hostname}")

    context = ssl.create_default_context()

    try:
        with socket.create_connection((hostname, port), timeout=timeout) as raw_socket:
            with context.wrap_socket(raw_socket, server_hostname=hostname) as tls_socket:
                certificate = tls_socket.getpeercert()

                print("TLS version:", tls_socket.version())
                print("Cipher:", tls_socket.cipher())
                print("ALPN:", tls_socket.selected_alpn_protocol())
                print("Peer certificate subject:", certificate.get("subject"))
                print("Peer certificate issuer:", certificate.get("issuer"))
                print("Certificate validity start:", certificate.get("notBefore"))
                print("Certificate validity end:", certificate.get("notAfter"))
                print("Subject alternative names:")
                for name in certificate.get("subjectAltName", []):
                    print(" ", name)

    except (OSError, ssl.SSLError) as exc:
        print("TLS inspection could not be completed:", exc)
        print("The educational examples remain usable without network access.")


# ============================================================================
# 15. CERTIFICATE VALIDATION CONCEPTS
# ============================================================================

def certificate_validation_checklist() -> None:
    section("15. CERTIFICATE VALIDATION")

    checks = [
        "The certificate chain leads to a trusted root or trusted anchor.",
        "The certificate is currently valid according to its validity interval.",
        "The requested hostname matches an appropriate Subject Alternative Name.",
        "The certificate is appropriate for server authentication.",
        "Cryptographic signatures and chain relationships validate.",
        "Revocation status may be checked according to the client's security policy.",
        "The TLS protocol and cipher configuration meet security requirements.",
    ]

    for number, check in enumerate(checks, 1):
        print(f"{number}. {check}")

    print("\nNever disable certificate verification merely to make a TLS connection work.")
    print("That removes a central part of HTTPS server authentication.")


# ============================================================================
# 16. PYTHON HTTPS CLIENT
# ============================================================================

def https_get(
    hostname: str,
    path: str = "/",
    timeout: float = 5.0,
) -> Tuple[int, Dict[str, str], bytes]:
    context = ssl.create_default_context()

    connection = http.client.HTTPSConnection(
        hostname,
        timeout=timeout,
        context=context,
    )

    try:
        connection.request(
            "GET",
            path,
            headers={
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.1",
                "User-Agent": "HTTPStudyClient/1.0",
                "Connection": "close",
            },
        )

        response = connection.getresponse()
        headers = {key: value for key, value in response.getheaders()}
        body = response.read()

        return response.status, headers, body
    finally:
        connection.close()


def demonstrate_https_client() -> None:
    section("16. PYTHON HTTPS CLIENT")

    try:
        status, headers, body = https_get("example.com", "/")
        print("Status:", status)
        print("Content-Type:", headers.get("Content-Type"))
        print("Body bytes received:", len(body))
        print("First 200 bytes:")
        print(body[:200].decode("utf-8", errors="replace"))
    except (OSError, ssl.SSLError) as exc:
        print("HTTPS request could not be completed:", exc)


# ============================================================================
# 17. URLLIB AND SAFE REQUEST CONSTRUCTION
# ============================================================================

def demonstrate_urllib() -> None:
    section("17. URLLIB REQUEST CONSTRUCTION")

    url = "https://example.com/?q=" + urllib.parse.quote("HTTP and HTTPS")

    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "text/html",
            "User-Agent": "HTTPStudyClient/1.0",
        },
    )

    print("Prepared URL:", request.full_url)
    print("Prepared method:", request.method)
    print("Prepared headers:", dict(request.header_items()))


# ============================================================================
# 18. AUTHENTICATION ENCODING EXAMPLE
# ============================================================================

def basic_auth_header(username: str, password: str) -> str:
    credentials = f"{username}:{password}".encode("utf-8")
    encoded = base64.b64encode(credentials).decode("ascii")
    return f"Basic {encoded}"


def demonstrate_authentication() -> None:
    section("18. AUTHENTICATION CONCEPTS")

    header = basic_auth_header("alice", "example-password")
    print("Example Basic authorization header:")
    print(header)

    print("\nBase64 is encoding, not encryption.")
    print("Basic authentication therefore requires a protected transport such as HTTPS.")
    print("Production systems frequently use short-lived tokens, sessions, OAuth-style")
    print("authorization mechanisms, or other application-specific authentication designs.")


# ============================================================================
# 19. REQUEST VALIDATION
# ============================================================================

def validate_http_request(
    method: str,
    target: str,
    headers: Mapping[str, str],
    body: bytes,
) -> List[str]:
    errors: List[str] = []

    if method.upper() not in COMMON_METHODS:
        errors.append(f"Unsupported method: {method}")

    if not target.startswith(("/", "http://", "https://")):
        errors.append("Target must be an origin-form path or absolute URL.")

    if "Host" not in headers and "host" not in {key.lower() for key in headers}:
        errors.append("HTTP/1.1 requests require a Host header.")

    if "Content-Length" in headers:
        try:
            declared_length = int(headers["Content-Length"])
            if declared_length != len(body):
                errors.append("Content-Length does not match body length.")
        except ValueError:
            errors.append("Content-Length is not an integer.")

    return errors


def demonstrate_validation() -> None:
    section("19. REQUEST VALIDATION")

    headers = {
        "Host": "api.example.com",
        "Content-Length": "5",
    }
    body = b"hello"

    print("Valid request errors:", validate_http_request("POST", "/users", headers, body))

    invalid_headers = {
        "Host": "api.example.com",
        "Content-Length": "100",
    }

    print(
        "Invalid request errors:",
        validate_http_request("POST", "/users", invalid_headers, body),
    )


# ============================================================================
# 20. RATE LIMITING
# ============================================================================

class TokenBucket:
    """
    Simple token-bucket rate limiter.

    Tokens accumulate at refill_rate tokens per second up to capacity.
    Each accepted operation consumes one token.
    """

    def __init__(self, capacity: float, refill_rate: float) -> None:
        if capacity <= 0 or refill_rate <= 0:
            raise ValueError("capacity and refill_rate must be positive")

        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_update = time.monotonic()

    def allow(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_update
        self.last_update = now

        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate,
        )

        if self.tokens >= cost:
            self.tokens -= cost
            return True

        return False


def demonstrate_rate_limiting() -> None:
    section("20. RATE LIMITING")

    limiter = TokenBucket(capacity=3, refill_rate=1)

    for attempt in range(5):
        print(f"Request {attempt + 1}: allowed={limiter.allow()}")


# ============================================================================
# 21. SECURITY HEADERS
# ============================================================================

def demonstrate_security_headers() -> None:
    section("21. SECURITY-RELATED RESPONSE HEADERS")

    security_headers = {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'; object-src 'none'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=()",
    }

    for name, value in security_headers.items():
        print(f"{name}: {value}")

    print("\nSecurity headers are defense-in-depth controls.")
    print("They do not replace correct server authorization, input validation, or TLS.")


# ============================================================================
# 22. REQUEST SMUGGLING / PARSING AMBIGUITY
# ============================================================================

def demonstrate_parsing_security() -> None:
    section("22. HTTP PARSING SECURITY")

    print("Proxy and origin servers must agree about request framing.")
    print("Ambiguous Content-Length and Transfer-Encoding handling can create")
    print("request-smuggling vulnerabilities.")
    print("\nDefensive principles:")
    print("1. Use maintained HTTP libraries.")
    print("2. Reject malformed or ambiguous requests.")
    print("3. Keep intermediary and origin parsing behavior compatible.")
    print("4. Avoid implementing HTTP parsing from scratch in production.")


# ============================================================================
# 23. PERFORMANCE CONSIDERATIONS
# ============================================================================

def demonstrate_performance_concepts() -> None:
    section("23. PERFORMANCE CONSIDERATIONS")

    concepts = {
        "Connection reuse": "Avoids repeatedly establishing transport/TLS connections.",
        "Keep-alive": "Allows multiple HTTP requests over an eligible connection.",
        "Compression": "Can reduce transfer size at CPU cost.",
        "Caching": "Can avoid repeated network and server work.",
        "HTTP/2": "Supports multiplexed streams and header compression over a connection.",
        "HTTP/3": "Uses QUIC over UDP and provides stream-oriented transport behavior.",
        "Payload size": "Smaller representations generally reduce transfer time and bandwidth.",
    }

    for name, description in concepts.items():
        print(f"{name:22}: {description}")


# ============================================================================
# 24. HTTP VERSION COMPARISON
# ============================================================================

def compare_versions() -> None:
    section("24. HTTP VERSION COMPARISON")

    rows = [
        ("HTTP/1.0", "Basic persistent-connection history; older deployments.", "Legacy"),
        ("HTTP/1.1", "Persistent connections, chunked transfer, Host header.", "Widely understood"),
        ("HTTP/2", "Binary framing, multiplexed streams, HPACK header compression.", "Modern web"),
        ("HTTP/3", "HTTP semantics over QUIC; QPACK header compression.", "Modern QUIC-based web"),
    ]

    for version, mechanisms, context in rows:
        print(f"{version:10} | {mechanisms:70} | {context}")


# ============================================================================
# 25. TLS CONFIGURATION INSPECTION
# ============================================================================

def demonstrate_local_tls_configuration() -> None:
    section("25. LOCAL TLS CONFIGURATION")

    context = ssl.create_default_context()

    print("OpenSSL version:", ssl.OPENSSL_VERSION)
    print("Minimum configured TLS version:", context.minimum_version)
    print("Maximum configured TLS version:", context.maximum_version)
    print("Certificate verification mode:", context.verify_mode)
    print("Hostname checking:", context.check_hostname)

    print("\nSelected secure defaults are preferable to manually weakening verification.")


# ============================================================================
# 26. SIMPLE HTTP ROUTING MODEL
# ============================================================================

@dataclass
class Route:
    method: str
    pattern: str
    handler_name: str


class Router:
    def __init__(self) -> None:
        self.routes: List[Route] = []

    def add(self, method: str, pattern: str, handler_name: str) -> None:
        self.routes.append(Route(method.upper(), pattern, handler_name))

    def resolve(self, method: str, path: str) -> Optional[Route]:
        method = method.upper()

        for route in self.routes:
            if route.method != method:
                continue

            regex = re.sub(r"<[^>]+>", r"[^/]+", route.pattern)
            if re.fullmatch(regex, path):
                return route

        return None


def demonstrate_routing() -> None:
    section("26. APPLICATION ROUTING")

    router = Router()
    router.add("GET", r"/users/<id>", "get_user")
    router.add("POST", r"/users", "create_user")
    router.add("DELETE", r"/users/<id>", "delete_user")

    tests = [
        ("GET", "/users/42"),
        ("POST", "/users"),
        ("DELETE", "/users/42"),
        ("GET", "/products/10"),
    ]

    for method, path in tests:
        route = router.resolve(method, path)
        print(method, path, "->", route.handler_name if route else "404 Not Found")


# ============================================================================
# 27. ERROR RESPONSE DESIGN
# ============================================================================

def error_response(status: int, message: str, request_id: str) -> HttpResponse:
    payload = json.dumps(
        {
            "error": {
                "code": status,
                "message": message,
                "request_id": request_id,
            }
        }
    ).encode("utf-8")

    return HttpResponse(
        status_code=status,
        reason=HTTPStatus(status).phrase,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
            "Cache-Control": "no-store",
        },
        body=payload,
    )


def demonstrate_error_design() -> None:
    section("27. API ERROR RESPONSE DESIGN")

    response = error_response(404, "User was not found.", "req-20260928-001")

    print(f"HTTP/1.1 {response.status_code} {response.reason}")
    for key, value in response.headers.items():
        print(f"{key}: {value}")
    print()
    print(response.body.decode())


# ============================================================================
# 28. OBSERVABILITY
# ============================================================================

def demonstrate_observability() -> None:
    section("28. HTTP OBSERVABILITY")

    log_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "GET",
        "path": "/api/users/42",
        "status": 200,
        "duration_ms": 18.4,
        "request_id": "req-12345",
        "bytes_sent": 842,
        "user_agent": "ExampleClient/2.0",
    }

    print(json.dumps(log_record, indent=2))

    print("\nUseful production metrics:")
    print("- request rate")
    print("- latency percentiles such as p50, p95, and p99")
    print("- status-code distribution")
    print("- error rate")
    print("- response size")
    print("- TLS handshake failures")
    print("- upstream timeout rate")


# ============================================================================
# 29. HTTP/HTTPS DIAGNOSTIC CHECKLIST
# ============================================================================

def diagnostic_checklist() -> None:
    section("29. HTTP/HTTPS DIAGNOSTIC CHECKLIST")

    checklist = [
        "Confirm DNS resolves to the expected service.",
        "Confirm TCP connectivity to the intended port.",
        "For HTTPS, verify TLS negotiation succeeds.",
        "Check certificate hostname and validity.",
        "Inspect the HTTP status code.",
        "Inspect response headers.",
        "Check redirects and the final URL.",
        "Check request method and request body.",
        "Check Content-Type and Content-Length.",
        "Check authentication and authorization separately.",
        "Check server and proxy logs using a request identifier.",
        "Check timeout and retry behavior.",
        "Check rate-limit responses such as 429.",
        "Check caching and conditional-request behavior.",
    ]

    for item in checklist:
        print("[ ]", item)


# ============================================================================
# 30. COMMON MISTAKES
# ============================================================================

def common_mistakes() -> None:
    section("30. COMMON MISTAKES")

    mistakes = [
        ("Treating HTTP as encrypted", "HTTP itself does not provide TLS confidentiality."),
        ("Confusing 401 and 403", "Authentication and authorization are different concepts."),
        ("Trusting Base64", "Base64 provides representation, not confidentiality."),
        ("Disabling TLS verification", "This undermines server authentication."),
        ("Ignoring Content-Type", "Consumers may parse a body incorrectly."),
        ("Retrying every request blindly", "Non-idempotent operations may be duplicated."),
        ("Logging secrets", "Tokens, cookies, and credentials should not be exposed in logs."),
        ("Ignoring certificate hostname validation", "A valid certificate for another hostname is not sufficient."),
        ("Assuming 200 means business success", "Application-level success may require additional validation."),
    ]

    for mistake, correction in mistakes:
        print(f"{mistake}: {correction}")


# ============================================================================
# 31. MINI END-TO-END SIMULATION
# ============================================================================

def simulate_secure_api_flow() -> None:
    section("31. END-TO-END HTTPS API FLOW")

    print("1. Client resolves api.example.com.")
    print("2. Client opens a network connection.")
    print("3. TLS handshake negotiates a secure session.")
    print("4. Client validates the server certificate and hostname.")
    print("5. Client sends an HTTP request through the protected TLS channel.")
    print("6. Server authenticates the client if required.")
    print("7. Server authorizes the requested operation.")
    print("8. Server validates request data.")
    print("9. Server performs the application operation.")
    print("10. Server returns an HTTP response.")
    print("11. Client checks status, headers, and response data.")
    print("12. Connection may remain available for additional requests.")


# ============================================================================
# 32. MAIN PROGRAM
# ============================================================================

def main() -> None:
    explain_http_terms()
    demonstrate_raw_messages()
    demonstrate_methods()
    demonstrate_status_codes()
    demonstrate_headers()
    demonstrate_url_structure()
    demonstrate_bodies()
    demonstrate_cookies()
    demonstrate_caching()
    demonstrate_content_negotiation()
    demonstrate_redirects()
    demonstrate_http_security()
    demonstrate_tls_concepts()
    certificate_validation_checklist()
    demonstrate_urllib()
    demonstrate_authentication()
    demonstrate_validation()
    demonstrate_rate_limiting()
    demonstrate_security_headers()
    demonstrate_parsing_security()
    demonstrate_performance_concepts()
    compare_versions()
    demonstrate_local_tls_configuration()
    demonstrate_routing()
    demonstrate_error_design()
    demonstrate_observability()
    diagnostic_checklist()
    common_mistakes()
    simulate_secure_api_flow()

    # Network demonstrations are isolated so that lack of Internet access
    # does not prevent the educational program from running.
    inspect_certificate("example.com")
    demonstrate_https_client()


if __name__ == "__main__":
    main()
