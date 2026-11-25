import re
from collections.abc import Mapping

SENSITIVE_KEYS = re.compile(
    r"password|passwd|credential|community|privatekey|token|apikey|accesskey|secret|authorization|"
    r"cookie|passphrase|^pwd$|^auth$|^sshkey$|^enablepass|^bearer$|^psk$|^authkey$|^privkey$"
)
PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|\Z)",
    re.IGNORECASE | re.DOTALL,
)
ASSIGNMENT = re.compile(
    r"""(?i)\b(?:snmp[-_ ]+community(?:[-_ ]+string)?|community(?:[-_ ]+string)?|"""
    r"""raw[-_ ]*password|password|passwd|pwd|passphrase|credentials?|api[-_ ]*key|"""
    r"""access[-_ ]*token|refresh[-_ ]*token|token|secret|authorization|private[-_ ]*key)"""
    r"""["']?\s*(?:[:=]|\bis\b)\s*(?:bearer\s+)?(?:"[^"]*"|'[^']*'|[^\s,;}`"']+)"""
)
SNMP_FLAG = re.compile(r"""(?i)(\bsnmp(?:get|walk|bulkwalk|set)\b[^\n;]*?\s-c\s*)(?:"[^"]*"|'[^']*'|[^\s;]+)""")
SNMP_CONFIG = re.compile(
    r"""(?i)(\b(?:snmp-server\s+community|rocommunity6?|rwcommunity6?)\s+)(?:"[^"]*"|'[^']*'|[^\s;]+)"""
)
URL_CREDENTIAL = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^/\s@]+@", re.IGNORECASE)
TOKEN = re.compile(
    r"(?i)\bbearer\s+[\w.~/+=-]+|\b(?:sk-(?:proj-)?|gh[pousr]_|github_pat_|AIza|xox[bpars]-)"
    r"[\w-]{12,}|\beyJ[\w-]+\.[\w-]+\.[\w-]+"
)


def sanitize_context(payload):
    if isinstance(payload, Mapping):
        return {
            key: sanitize_context(value) for key, value in payload.items()
            if isinstance(key, str) and not SENSITIVE_KEYS.search(re.sub(r"[^a-z0-9]", "", key.lower()))
        }
    if isinstance(payload, (list, tuple)):
        return [sanitize_context(value) for value in payload]
    if isinstance(payload, str):
        value = PRIVATE_KEY.sub("[REDACTED]", payload)
        value = URL_CREDENTIAL.sub(r"\1", value)
        value = SNMP_FLAG.sub(r"\1[REDACTED]", value)
        value = SNMP_CONFIG.sub(r"\1[REDACTED]", value)
        value = ASSIGNMENT.sub("[REDACTED]", value)
        return TOKEN.sub("[REDACTED]", value)
    return payload
