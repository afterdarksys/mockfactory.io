"""
DNS Record Model - Fake authoritative DNS for testing
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class DNSRecordType(str, enum.Enum):
    """Supported DNS record types"""
    A = "A"              # IPv4 address
    AAAA = "AAAA"        # IPv6 address
    CNAME = "CNAME"      # Canonical name
    MX = "MX"            # Mail exchange
    TXT = "TXT"          # Text record
    NS = "NS"            # Name server
    SRV = "SRV"          # Service record
    PTR = "PTR"          # Pointer record
    SOA = "SOA"          # Start of authority


class DNSRecord(Base):
    """
    DNS Record for fake authoritative DNS server

    Allows users to create DNS records for their environment
    that can be queried by applications running tests

    Example:
    - Name: api.myapp.dev
    - Type: A
    - Value: 192.168.1.100
    - TTL: 300
    """
    __tablename__ = "dns_records"

    id = Column(Integer, primary_key=True, index=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)
    name = Column(String, nullable=False, index=True)  # Fully qualified domain name
    record_type = Column(Enum(DNSRecordType), nullable=False)
    value = Column(String, nullable=False)  # IP address, hostname, text, etc.
    ttl = Column(Integer, default=300, nullable=False)  # Time to live in seconds
    priority = Column(Integer, nullable=True)  # For MX and SRV records
    weight = Column(Integer, nullable=True)   # For SRV records
    port = Column(Integer, nullable=True)     # For SRV records
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    environment = relationship("Environment", back_populates="dns_records")

    # Composite index for fast lookups
    __table_args__ = (
        Index('ix_dns_name_type', 'name', 'record_type'),
        Index('ix_dns_env_name', 'environment_id', 'name'),
    )

    def to_dns_response(self) -> dict:
        """
        Convert to DNS response format

        Returns dict suitable for DNS server response
        """
        response = {
            "name": self.name,
            "type": self.record_type.value,
            "value": self.value,
            "ttl": self.ttl
        }

        # Add optional fields for MX/SRV records
        if self.priority is not None:
            response["priority"] = self.priority
        if self.weight is not None:
            response["weight"] = self.weight
        if self.port is not None:
            response["port"] = self.port

        return response

    def __repr__(self):
        return f"<DNSRecord {self.name} {self.record_type.value} -> {self.value}>"
