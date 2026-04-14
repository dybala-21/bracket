from __future__ import annotations


class BracketError(Exception):
    pass


class ContractError(BracketError):
    pass


class EvidenceError(BracketError):
    pass


class PolicyError(BracketError):
    pass


class VerdictError(BracketError):
    pass


class ProbeError(BracketError):
    pass


class ReplayError(BracketError):
    pass


class AdapterError(BracketError):
    pass
