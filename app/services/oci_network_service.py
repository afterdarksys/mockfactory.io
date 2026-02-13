"""
OCI Network Service
Creates REAL OCI VCNs/Subnets for mock AWS VPCs
ISOLATED in dedicated compartment away from core infrastructure
"""
import oci
import os
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class OCINetworkService:
    """
    Manages OCI networking resources for AWS VPC emulation
    All resources created in ISOLATED compartment: 'mock-aws-compartment'
    """

    def __init__(self):
        """Initialize OCI clients"""
        # Load OCI config
        self.config = oci.config.from_file()

        # Network client
        self.vcn_client = oci.core.VirtualNetworkClient(self.config)

        # Identity client (for compartment management)
        self.identity_client = oci.identity.IdentityClient(self.config)

        # Get or create isolated compartment for mock AWS resources
        self.mock_compartment_id = self._get_mock_compartment()

        logger.info(f"OCI Network Service initialized. Mock compartment: {self.mock_compartment_id}")

    def _get_mock_compartment(self) -> str:
        """
        Get or create 'mock-aws-compartment' for isolation
        This keeps mock AWS resources away from production MockFactory infrastructure
        """
        root_compartment_id = self.config["tenancy"]

        try:
            # List compartments
            compartments = self.identity_client.list_compartments(
                compartment_id=root_compartment_id
            ).data

            # Look for existing mock compartment
            for comp in compartments:
                if comp.name == "mock-aws-compartment" and comp.lifecycle_state == "ACTIVE":
                    logger.info(f"Found existing mock compartment: {comp.id}")
                    return comp.id

            # Create new compartment if not found
            logger.info("Creating new isolated compartment for mock AWS resources...")
            compartment_details = oci.identity.models.CreateCompartmentDetails(
                compartment_id=root_compartment_id,
                name="mock-aws-compartment",
                description="Isolated compartment for MockFactory AWS VPC emulation. Firewalled from core infrastructure."
            )

            new_compartment = self.identity_client.create_compartment(
                compartment_details
            ).data

            logger.info(f"Created mock compartment: {new_compartment.id}")
            return new_compartment.id

        except Exception as e:
            logger.error(f"Error managing mock compartment: {e}")
            # Fallback to root compartment (not ideal but prevents crashes)
            logger.warning("Falling back to root compartment - REVIEW ISOLATION!")
            return root_compartment_id

    def create_vcn(self, cidr_block: str, display_name: str, dns_label: Optional[str] = None) -> Dict:
        """
        Create REAL OCI VCN for AWS VPC

        Args:
            cidr_block: CIDR block (e.g., "10.0.0.0/16")
            display_name: VCN name
            dns_label: Optional DNS label

        Returns:
            Dict with VCN details including OCID
        """
        try:
            logger.info(f"Creating OCI VCN in isolated compartment: {cidr_block}")

            vcn_details = oci.core.models.CreateVcnDetails(
                compartment_id=self.mock_compartment_id,
                cidr_block=cidr_block,
                display_name=display_name,
                dns_label=dns_label,
                is_ipv6_enabled=False
            )

            vcn = self.vcn_client.create_vcn(vcn_details).data

            logger.info(f"Created VCN: {vcn.id}")

            return {
                "vcn_id": vcn.id,
                "cidr_block": vcn.cidr_block,
                "display_name": vcn.display_name,
                "lifecycle_state": vcn.lifecycle_state,
                "compartment_id": vcn.compartment_id
            }

        except Exception as e:
            logger.error(f"Error creating VCN: {e}")
            raise

    def create_subnet(
        self,
        vcn_id: str,
        cidr_block: str,
        display_name: str,
        availability_domain: Optional[str] = None,
        dns_label: Optional[str] = None,
        prohibit_public_ip: bool = False
    ) -> Dict:
        """
        Create REAL OCI Subnet for AWS Subnet

        Args:
            vcn_id: Parent VCN OCID
            cidr_block: Subnet CIDR (e.g., "10.0.1.0/24")
            display_name: Subnet name
            availability_domain: AD (optional, can be regional)
            dns_label: Optional DNS label
            prohibit_public_ip: True for private subnet

        Returns:
            Dict with Subnet details including OCID
        """
        try:
            logger.info(f"Creating OCI Subnet in VCN {vcn_id}: {cidr_block}")

            subnet_details = oci.core.models.CreateSubnetDetails(
                compartment_id=self.mock_compartment_id,
                vcn_id=vcn_id,
                cidr_block=cidr_block,
                display_name=display_name,
                dns_label=dns_label,
                prohibit_public_ip_on_vnic=prohibit_public_ip,
                # Use regional subnet (not tied to specific AD)
                availability_domain=availability_domain
            )

            subnet = self.vcn_client.create_subnet(subnet_details).data

            logger.info(f"Created Subnet: {subnet.id}")

            return {
                "subnet_id": subnet.id,
                "vcn_id": subnet.vcn_id,
                "cidr_block": subnet.cidr_block,
                "display_name": subnet.display_name,
                "lifecycle_state": subnet.lifecycle_state,
                "availability_domain": subnet.availability_domain
            }

        except Exception as e:
            logger.error(f"Error creating subnet: {e}")
            raise

    def create_internet_gateway(self, vcn_id: str, display_name: str) -> Dict:
        """
        Create REAL OCI Internet Gateway for AWS IGW

        Args:
            vcn_id: VCN OCID
            display_name: Gateway name

        Returns:
            Dict with IGW details
        """
        try:
            logger.info(f"Creating Internet Gateway for VCN {vcn_id}")

            igw_details = oci.core.models.CreateInternetGatewayDetails(
                compartment_id=self.mock_compartment_id,
                vcn_id=vcn_id,
                display_name=display_name,
                is_enabled=True
            )

            igw = self.vcn_client.create_internet_gateway(igw_details).data

            logger.info(f"Created Internet Gateway: {igw.id}")

            return {
                "igw_id": igw.id,
                "vcn_id": igw.vcn_id,
                "is_enabled": igw.is_enabled,
                "lifecycle_state": igw.lifecycle_state
            }

        except Exception as e:
            logger.error(f"Error creating internet gateway: {e}")
            raise

    def create_network_security_group(self, vcn_id: str, display_name: str) -> Dict:
        """
        Create REAL OCI Network Security Group for AWS Security Group

        Args:
            vcn_id: VCN OCID
            display_name: NSG name

        Returns:
            Dict with NSG details
        """
        try:
            logger.info(f"Creating Network Security Group for VCN {vcn_id}")

            nsg_details = oci.core.models.CreateNetworkSecurityGroupDetails(
                compartment_id=self.mock_compartment_id,
                vcn_id=vcn_id,
                display_name=display_name
            )

            nsg = self.vcn_client.create_network_security_group(nsg_details).data

            logger.info(f"Created NSG: {nsg.id}")

            return {
                "nsg_id": nsg.id,
                "vcn_id": nsg.vcn_id,
                "lifecycle_state": nsg.lifecycle_state
            }

        except Exception as e:
            logger.error(f"Error creating NSG: {e}")
            raise

    def add_nsg_rule(
        self,
        nsg_id: str,
        direction: str,  # "INGRESS" or "EGRESS"
        protocol: str,  # "6" (TCP), "17" (UDP), "1" (ICMP), "all"
        source_cidr: Optional[str] = None,
        destination_cidr: Optional[str] = None,
        tcp_options: Optional[Dict] = None,
        udp_options: Optional[Dict] = None
    ) -> Dict:
        """
        Add security rule to NSG

        Args:
            nsg_id: Network Security Group OCID
            direction: INGRESS or EGRESS
            protocol: Protocol number or "all"
            source_cidr: Source CIDR (for ingress)
            destination_cidr: Dest CIDR (for egress)
            tcp_options: TCP port range
            udp_options: UDP port range

        Returns:
            Dict with rule details
        """
        try:
            # Convert protocol
            if protocol == "tcp":
                protocol = "6"
            elif protocol == "udp":
                protocol = "17"
            elif protocol == "icmp":
                protocol = "1"
            elif protocol == "-1" or protocol == "all":
                protocol = "all"

            rule_details = oci.core.models.AddNetworkSecurityGroupSecurityRulesDetails(
                security_rules=[
                    oci.core.models.AddSecurityRuleDetails(
                        direction=direction,
                        protocol=protocol,
                        source=source_cidr,
                        destination=destination_cidr,
                        tcp_options=tcp_options,
                        udp_options=udp_options,
                        description=f"AWS SG rule - {direction}"
                    )
                ]
            )

            result = self.vcn_client.add_network_security_group_security_rules(
                network_security_group_id=nsg_id,
                add_network_security_group_security_rules_details=rule_details
            ).data

            logger.info(f"Added rule to NSG {nsg_id}: {direction} {protocol}")

            return {"success": True, "rule_count": len(result.security_rules)}

        except Exception as e:
            logger.error(f"Error adding NSG rule: {e}")
            raise

    def delete_vcn(self, vcn_id: str) -> bool:
        """
        Delete OCI VCN (and all dependent resources)

        Args:
            vcn_id: VCN OCID to delete

        Returns:
            True if successful
        """
        try:
            logger.info(f"Deleting VCN: {vcn_id}")

            # Delete dependent resources first
            # (subnets, IGWs, route tables, etc.)
            # OCI requires cleanup in specific order

            # Delete subnets
            subnets = self.vcn_client.list_subnets(
                compartment_id=self.mock_compartment_id,
                vcn_id=vcn_id
            ).data

            for subnet in subnets:
                logger.info(f"Deleting subnet: {subnet.id}")
                self.vcn_client.delete_subnet(subnet.id)

            # Delete internet gateways
            igws = self.vcn_client.list_internet_gateways(
                compartment_id=self.mock_compartment_id,
                vcn_id=vcn_id
            ).data

            for igw in igws:
                logger.info(f"Deleting IGW: {igw.id}")
                self.vcn_client.delete_internet_gateway(igw.id)

            # Delete NSGs
            nsgs = self.vcn_client.list_network_security_groups(
                compartment_id=self.mock_compartment_id,
                vcn_id=vcn_id
            ).data

            for nsg in nsgs:
                logger.info(f"Deleting NSG: {nsg.id}")
                self.vcn_client.delete_network_security_group(nsg.id)

            # Finally delete VCN
            self.vcn_client.delete_vcn(vcn_id)
            logger.info(f"VCN deleted: {vcn_id}")

            return True

        except Exception as e:
            logger.error(f"Error deleting VCN: {e}")
            return False

    def delete_subnet(self, subnet_id: str) -> bool:
        """Delete OCI Subnet"""
        try:
            self.vcn_client.delete_subnet(subnet_id)
            logger.info(f"Subnet deleted: {subnet_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting subnet: {e}")
            return False

    def delete_nsg(self, nsg_id: str) -> bool:
        """Delete OCI Network Security Group"""
        try:
            self.vcn_client.delete_network_security_group(nsg_id)
            logger.info(f"NSG deleted: {nsg_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting NSG: {e}")
            return False


# Singleton instance
_oci_network_service = None

def get_oci_network_service() -> OCINetworkService:
    """Get or create OCI Network Service singleton"""
    global _oci_network_service
    if _oci_network_service is None:
        _oci_network_service = OCINetworkService()
    return _oci_network_service
