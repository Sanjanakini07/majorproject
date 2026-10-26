"""Letting phones on the same Wi-Fi reach this laptop: its addresses, an HTTPS certificate, a QR code.

Phone browsers only allow the camera and microphone on https pages, so the
phone address uses a self-signed certificate made here. The phone shows a
warning once; tapping "Advanced > Proceed" opens the app.
"""
import datetime
import ipaddress
import io
import socket

from app.config import DATA_DIR

CERT = DATA_DIR / "lan-cert.pem"
KEY = DATA_DIR / "lan-key.pem"


def _main_ip() -> str | None:
    """The address of the network the laptop really uses (Wi-Fi), not VirtualBox/WSL adapters."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))  # UDP connect sends nothing; it only picks the route
            return s.getsockname()[0]
        except OSError:
            return None  # no network with a gateway, e.g. only the laptop's own hotspot


def lan_ips() -> list[str]:
    """This laptop's IPv4 addresses on local networks, the main one first."""
    ips = {info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    ips = sorted(ip for ip in ips if not ip.startswith(("127.", "169.254.")))
    main = _main_ip()
    return [main, *(ip for ip in ips if ip != main)] if main in ips else ips


def ensure_cert(ips: list[str]) -> None:
    """Make a self-signed certificate for these addresses, unless the current one already covers them."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    wanted = {ipaddress.ip_address(ip) for ip in ["127.0.0.1", *ips]}
    if CERT.exists() and KEY.exists():
        cert = x509.load_pem_x509_certificate(CERT.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        still_valid = cert.not_valid_after_utc > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
        if still_valid and wanted <= set(san.get_values_for_type(x509.IPAddress)):
            return

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NMAMIT Assistant (this laptop)")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), *map(x509.IPAddress, wanted)]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    KEY.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def qr_svg(text: str) -> str:
    import qrcode
    import qrcode.image.svg

    buf = io.BytesIO()
    qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2).save(buf)
    return buf.getvalue().decode()
