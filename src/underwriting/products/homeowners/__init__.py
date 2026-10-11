"""Homeowners product pack."""

from underwriting.products.contract import register_pack
from underwriting.products.homeowners.pack import HomeownersPack

register_pack("homeowners", HomeownersPack())

__all__ = ["HomeownersPack"]
