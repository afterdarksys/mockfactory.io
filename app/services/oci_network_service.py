"""
OCI Network Service — REMOVED.
VPC emulation now uses in-memory state in environment.oci_resources.
This stub exists only to prevent ImportError if old code references it.
"""


class OCINetworkService:
    def __getattr__(self, name):
        raise NotImplementedError(
            "OCINetworkService has been replaced by in-memory VPC emulation. "
            "See app/api/aws_vpc_emulator.py."
        )


def get_oci_network_service() -> OCINetworkService:
    raise NotImplementedError(
        "OCINetworkService has been replaced by in-memory VPC emulation. "
        "See app/api/aws_vpc_emulator.py."
    )
