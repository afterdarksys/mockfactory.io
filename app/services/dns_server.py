"""
Fake Authoritative DNS Server - For testing DNS-dependent applications

Provides a simple DNS server that responds to queries based on records
stored in the database. Applications can configure this as their DNS server.
"""
import asyncio
import logging
from typing import Optional, List, Dict
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine
import struct
import socket

from app.core.config import settings
from app.models.dns_record import DNSRecord, DNSRecordType

logger = logging.getLogger(__name__)


class DNSQueryType:
    """DNS query types"""
    A = 1      # IPv4
    NS = 2     # Name server
    CNAME = 5  # Canonical name
    SOA = 6    # Start of authority
    PTR = 12   # Pointer
    MX = 15    # Mail exchange
    TXT = 16   # Text
    AAAA = 28  # IPv6
    SRV = 33   # Service


class DNSServer:
    """
    Simple DNS server for testing

    Listens on UDP port 53 (requires sudo/root or port 5353 for non-root)
    Responds to DNS queries based on database records

    Usage:
    ```python
    server = DNSServer(db_url="postgresql://...")
    await server.start()
    ```
    """

    def __init__(self, port: int = 5353):
        """
        Initialize DNS server

        Args:
            port: UDP port to listen on (default 5353 for non-root)
                  Use 53 for standard DNS (requires root privileges)
        """
        self.port = port
        self.socket: Optional[socket.socket] = None

        # Create database session
        engine = create_engine(settings.DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db_session = SessionLocal

    def parse_dns_query(self, data: bytes) -> Optional[Dict]:
        """
        Parse DNS query packet

        Returns:
            Dict with transaction_id, query_name, query_type
            None if parsing fails
        """
        try:
            # DNS header is 12 bytes
            if len(data) < 12:
                return None

            # Transaction ID (2 bytes)
            transaction_id = struct.unpack('>H', data[0:2])[0]

            # Parse question section
            # Skip header (12 bytes), parse domain name
            offset = 12
            domain_parts = []

            while offset < len(data):
                length = data[offset]
                if length == 0:
                    offset += 1
                    break

                offset += 1
                domain_parts.append(data[offset:offset+length].decode('ascii'))
                offset += length

            domain_name = '.'.join(domain_parts)

            # Query type (2 bytes after domain name)
            if offset + 4 > len(data):
                return None

            query_type = struct.unpack('>H', data[offset:offset+2])[0]
            query_class = struct.unpack('>H', data[offset+2:offset+4])[0]

            return {
                'transaction_id': transaction_id,
                'query_name': domain_name,
                'query_type': query_type,
                'query_class': query_class,
                'raw_data': data
            }

        except Exception as e:
            logger.error(f"Failed to parse DNS query: {e}")
            return None

    def build_dns_response(
        self,
        transaction_id: int,
        query_name: str,
        query_type: int,
        records: List[DNSRecord]
    ) -> bytes:
        """
        Build DNS response packet

        Args:
            transaction_id: From original query
            query_name: Domain name queried
            query_type: DNS query type
            records: Matching DNS records from database

        Returns:
            DNS response packet as bytes
        """
        try:
            response = bytearray()

            # Header (12 bytes)
            # Transaction ID
            response.extend(struct.pack('>H', transaction_id))

            # Flags: Standard query response, no error
            # QR=1 (response), Opcode=0 (standard), AA=1 (authoritative), TC=0, RD=1, RA=1, Z=0, RCODE=0
            flags = 0x8580  # 1000 0101 1000 0000
            response.extend(struct.pack('>H', flags))

            # Question count
            response.extend(struct.pack('>H', 1))

            # Answer count
            response.extend(struct.pack('>H', len(records)))

            # Authority count
            response.extend(struct.pack('>H', 0))

            # Additional count
            response.extend(struct.pack('>H', 0))

            # Question section
            # Encode domain name
            for part in query_name.split('.'):
                response.append(len(part))
                response.extend(part.encode('ascii'))
            response.append(0)  # End of domain name

            # Query type and class
            response.extend(struct.pack('>H', query_type))
            response.extend(struct.pack('>H', 1))  # Class IN

            # Answer section
            for record in records:
                # Domain name (use pointer to question)
                response.extend(b'\xc0\x0c')

                # Type
                type_map = {
                    DNSRecordType.A: DNSQueryType.A,
                    DNSRecordType.AAAA: DNSQueryType.AAAA,
                    DNSRecordType.CNAME: DNSQueryType.CNAME,
                    DNSRecordType.MX: DNSQueryType.MX,
                    DNSRecordType.TXT: DNSQueryType.TXT,
                    DNSRecordType.NS: DNSQueryType.NS,
                    DNSRecordType.SRV: DNSQueryType.SRV,
                    DNSRecordType.PTR: DNSQueryType.PTR,
                }
                record_type = type_map.get(record.record_type, DNSQueryType.A)
                response.extend(struct.pack('>H', record_type))

                # Class (IN)
                response.extend(struct.pack('>H', 1))

                # TTL
                response.extend(struct.pack('>I', record.ttl))

                # RDATA
                if record.record_type == DNSRecordType.A:
                    # IPv4 address (4 bytes)
                    octets = [int(x) for x in record.value.split('.')]
                    rdata = bytes(octets)
                    response.extend(struct.pack('>H', len(rdata)))
                    response.extend(rdata)

                elif record.record_type == DNSRecordType.AAAA:
                    # IPv6 address (16 bytes)
                    # Simplified - just return zeros for now
                    rdata = b'\x00' * 16
                    response.extend(struct.pack('>H', len(rdata)))
                    response.extend(rdata)

                elif record.record_type == DNSRecordType.CNAME:
                    # Canonical name (encoded domain)
                    rdata = bytearray()
                    for part in record.value.split('.'):
                        rdata.append(len(part))
                        rdata.extend(part.encode('ascii'))
                    rdata.append(0)
                    response.extend(struct.pack('>H', len(rdata)))
                    response.extend(rdata)

                elif record.record_type == DNSRecordType.MX:
                    # Mail exchange (priority + hostname)
                    rdata = bytearray()
                    rdata.extend(struct.pack('>H', record.priority or 10))
                    for part in record.value.split('.'):
                        rdata.append(len(part))
                        rdata.extend(part.encode('ascii'))
                    rdata.append(0)
                    response.extend(struct.pack('>H', len(rdata)))
                    response.extend(rdata)

                elif record.record_type == DNSRecordType.TXT:
                    # Text record
                    text = record.value.encode('utf-8')
                    rdata = bytearray()
                    rdata.append(len(text))
                    rdata.extend(text)
                    response.extend(struct.pack('>H', len(rdata)))
                    response.extend(rdata)

                else:
                    # Default: return empty rdata
                    response.extend(struct.pack('>H', 0))

            return bytes(response)

        except Exception as e:
            logger.error(f"Failed to build DNS response: {e}")
            return self.build_error_response(transaction_id, 2)  # Server failure

    def build_error_response(self, transaction_id: int, rcode: int) -> bytes:
        """
        Build DNS error response

        Args:
            transaction_id: From original query
            rcode: Response code (0=no error, 1=format error, 2=server failure, 3=name error)
        """
        response = bytearray()

        # Header
        response.extend(struct.pack('>H', transaction_id))

        # Flags with error code
        flags = 0x8000 | rcode  # QR=1, RCODE=rcode
        response.extend(struct.pack('>H', flags))

        # No questions, answers, authority, or additional records
        response.extend(struct.pack('>H', 0))
        response.extend(struct.pack('>H', 0))
        response.extend(struct.pack('>H', 0))
        response.extend(struct.pack('>H', 0))

        return bytes(response)

    async def handle_query(self, data: bytes, addr: tuple) -> Optional[bytes]:
        """
        Handle DNS query

        Args:
            data: DNS query packet
            addr: (ip, port) of sender

        Returns:
            DNS response packet or None
        """
        query = self.parse_dns_query(data)
        if not query:
            logger.warning(f"Invalid DNS query from {addr}")
            return None

        logger.info(
            f"DNS query from {addr[0]}:{addr[1]} - "
            f"{query['query_name']} type={query['query_type']}"
        )

        # Look up records in database
        db = self.db_session()

        try:
            # Map query type to our record type
            type_map = {
                DNSQueryType.A: DNSRecordType.A,
                DNSQueryType.AAAA: DNSRecordType.AAAA,
                DNSQueryType.CNAME: DNSRecordType.CNAME,
                DNSQueryType.MX: DNSRecordType.MX,
                DNSQueryType.TXT: DNSRecordType.TXT,
                DNSQueryType.NS: DNSRecordType.NS,
                DNSQueryType.SRV: DNSRecordType.SRV,
                DNSQueryType.PTR: DNSRecordType.PTR,
            }

            record_type = type_map.get(query['query_type'])

            if not record_type:
                logger.warning(f"Unsupported query type: {query['query_type']}")
                return self.build_error_response(query['transaction_id'], 4)  # Not implemented

            # Query database
            records = db.query(DNSRecord).filter(
                DNSRecord.name == query['query_name'].lower(),
                DNSRecord.record_type == record_type
            ).all()

            if not records:
                logger.info(f"No records found for {query['query_name']}")
                return self.build_error_response(query['transaction_id'], 3)  # Name error

            # Build response
            response = self.build_dns_response(
                query['transaction_id'],
                query['query_name'],
                query['query_type'],
                records
            )

            logger.info(f"Responding with {len(records)} record(s)")
            return response

        except Exception as e:
            logger.error(f"Error handling DNS query: {e}")
            return self.build_error_response(query['transaction_id'], 2)  # Server failure

        finally:
            db.close()

    async def start(self):
        """
        Start DNS server

        Listens for UDP packets on configured port
        """
        logger.info(f"Starting DNS server on UDP port {self.port}...")

        # Create UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('0.0.0.0', self.port))
        self.socket.setblocking(False)

        logger.info(f"DNS server listening on 0.0.0.0:{self.port}")

        # Handle queries in loop
        while True:
            try:
                # Use asyncio to receive data
                data, addr = await asyncio.get_event_loop().sock_recvfrom(self.socket, 512)

                # Handle query
                response = await self.handle_query(data, addr)

                if response:
                    # Send response
                    await asyncio.get_event_loop().sock_sendto(self.socket, response, addr)

            except asyncio.CancelledError:
                logger.info("DNS server shutting down...")
                break

            except Exception as e:
                logger.error(f"Error in DNS server loop: {e}")
                await asyncio.sleep(0.1)

    def stop(self):
        """Stop DNS server"""
        if self.socket:
            self.socket.close()
            logger.info("DNS server stopped")


# Global DNS server instance
dns_server: Optional[DNSServer] = None


async def start_dns_server(port: int = 5353):
    """
    Start DNS server as background task

    Args:
        port: UDP port (default 5353 for non-root, use 53 for standard DNS)
    """
    global dns_server

    dns_server = DNSServer(port=port)
    await dns_server.start()


def stop_dns_server():
    """Stop DNS server"""
    global dns_server

    if dns_server:
        dns_server.stop()
        dns_server = None
