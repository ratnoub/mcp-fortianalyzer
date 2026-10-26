"""Device Manager (DVM) tools for FortiAnalyzer.

Based on FNDN FortiAnalyzer 7.6.4 DVM and DVMDB API specifications.
Provides device management operations including add/delete devices
and device group management.
"""

import logging
from typing import Any

from mcp_fortianalyzer.api.client import FortiAnalyzerClient
from mcp_fortianalyzer.query.fields import coerce_value, get_vocabulary
from mcp_fortianalyzer.query.filters import FilterCondition, compile_to_array
from mcp_fortianalyzer.query.shape import resolve_projection
from mcp_fortianalyzer.server import get_faz_client, mcp
from mcp_fortianalyzer.tool_annotations import READ_ONLY
from mcp_fortianalyzer.utils.responses import error_response, redact
from mcp_fortianalyzer.utils.validation import (
    ValidationError,
    get_default_adom,
    sanitize_for_logging,
    validate_adom,
    validate_device_name,
)

logger = logging.getLogger(__name__)


def _get_client() -> FortiAnalyzerClient:
    """Get the FortiAnalyzer client instance."""
    client = get_faz_client()
    if not client:
        raise RuntimeError("FortiAnalyzer client not initialized")
    return client


def _os_version_conditions(version: str) -> list[FilterCondition]:
    """Exact-match conditions for a "major[.minor[.patch]]" firmware version.

    dvmdb stores the version split across three integers, ``os_ver`` (7),
    ``mr`` (6) and ``patch`` (7), so no single field holds "7.6", and ``like``
    does not text-match an integer at all: measured on 7.6.7 (#146), the old
    ``["os_ver", "like", "%7%"]`` returned seven devices, all with
    ``os_ver=0``, and none of the four on 7.

    ``str.isdigit`` alone is not enough: it is true for a superscript two,
    which ``int()`` then rejects, and for Arabic-Indic digits, which ``int()``
    reads as Western ones, so each part must be ASCII as well.

    Raises:
        ValidationError: unless the version is one to three dot-separated
            ASCII integers, optionally prefixed with "v".
    """
    parts = version.strip().lower().removeprefix("v").split(".")
    if not 1 <= len(parts) <= 3 or not all(p.isascii() and p.isdigit() for p in parts):
        raise ValidationError(
            f"Invalid os_version_filter '{version}'. Expected major[.minor[.patch]], e.g. '7.6'."
        )
    fields = ("os_ver", "mr", "patch")
    return [
        FilterCondition(field=field, op="eq", value=int(part))
        for field, part in zip(fields, parts, strict=False)
    ]


# =============================================================================
# Device Query Operations (DVMDB)
# =============================================================================


@mcp.tool(annotations=READ_ONLY)
async def list_device_groups(
    adom: str | None = None,
) -> dict[str, Any]:
    """List all device groups in an ADOM.

    Device groups allow organizing devices for policy and log management.

    Args:
        adom: ADOM name (default: from config DEFAULT_ADOM)

    Returns:
        dict: Device groups with keys:
            - status: "success" or "error"
            - count: Number of groups
            - groups: List of device group objects
            - message: Error message if failed

    Example:
        >>> result = await list_device_groups("root")
        >>> for group in result['groups']:
        ...     print(f"Group: {group['name']}")
    """
    try:
        adom = validate_adom(adom or get_default_adom())
        client = _get_client()
        groups = await client.list_device_groups(adom)

        return {
            "status": "success",
            "count": len(groups),
            "groups": groups,
        }
    except Exception as e:
        logger.error(f"Failed to list device groups: {e}")
        return {"status": "error", "message": redact(str(e))}


@mcp.tool(annotations=READ_ONLY)
async def list_device_vdoms(
    device: str,
    adom: str | None = None,
) -> dict[str, Any]:
    """List VDOMs for a specific device.

    Virtual Domains (VDOMs) are independent virtual instances
    within a FortiGate device.

    Args:
        device: Device name
        adom: ADOM name (default: from config DEFAULT_ADOM)

    Returns:
        dict: VDOM list with keys:
            - status: "success" or "error"
            - count: Number of VDOMs
            - vdoms: List of VDOM objects
            - message: Error message if failed

    Example:
        >>> result = await list_device_vdoms("FGT-HQ", "root")
        >>> for vdom in result['vdoms']:
        ...     print(f"VDOM: {vdom['name']}")
    """
    try:
        adom = validate_adom(adom or get_default_adom())
        device = validate_device_name(device)
        client = _get_client()
        vdoms = await client.list_device_vdoms(device, adom)

        return {
            "status": "success",
            "count": len(vdoms),
            "vdoms": vdoms,
        }
    except Exception as e:
        logger.error(f"Failed to list VDOMs for device {device}: {e}")
        return {"status": "error", "message": redact(str(e))}


# =============================================================================
# Device Management Operations (DVM)
# =============================================================================


@mcp.tool(annotations=READ_ONLY)
async def get_device_info(
    device: str,
    adom: str | None = None,
    include_vdoms: bool = False,
) -> dict[str, Any]:
    """Get detailed information about a specific device.

    Retrieves full device configuration and status.

    Args:
        device: Device name
        adom: ADOM name (default: from config DEFAULT_ADOM)
        include_vdoms: Include VDOM information (default: False)

    Returns:
        dict: Device details with keys:
            - status: "success" or "error"
            - device: Full device configuration object
            - vdoms: VDOM list (if include_vdoms=True)
            - message: Error message if failed

    Example:
        >>> result = await get_device_info("FGT-HQ", include_vdoms=True)
        >>> print(f"Version: {result['device']['os_ver']}")
        >>> print(f"Platform: {result['device']['platform_str']}")
    """
    try:
        adom = validate_adom(adom or get_default_adom())
        device = validate_device_name(device)
        client = _get_client()
        device_data = await client.get_device(device, adom, loadsub=1)

        result: dict[str, Any] = {
            "status": "success",
            # DVMDB device objects carry credential material (adm_pass, etc.);
            # mask it before returning over MCP.
            "device": sanitize_for_logging(device_data),
        }

        if include_vdoms:
            vdoms = await client.list_device_vdoms(device, adom)
            result["vdoms"] = vdoms

        return result
    except Exception as e:
        logger.error(f"Failed to get device info for {device}: {e}")
        return {"status": "error", "message": redact(str(e))}


@mcp.tool(annotations=READ_ONLY)
async def search_devices(
    adom: str | None = None,
    name_filter: str | None = None,
    platform_filter: str | None = None,
    os_version_filter: str | None = None,
    connection_status: str | None = None,
    filters: list[FilterCondition] | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Search for devices with filters.

    Args:
        adom: ADOM name (default: from config DEFAULT_ADOM)
        name_filter: Filter by device name (partial match)
        platform_filter: Filter by platform type (partial match)
        os_version_filter: Filter by firmware version, "major[.minor[.patch]]"
            ("7", "7.6", "7.6.7", an optional leading "v"). dvmdb stores the
            version as three integers, so this compiles to exact matches on
            os_ver, mr and patch -- "7.6" matches every 7.6.x. Anything else
            is refused before a request is sent.
        connection_status: Filter by connection status ("up", "down").
            Caution: FortiAnalyzer commonly stores conn_status 0 ("unknown")
            for log-only devices, so filtering "up"/"down" can match nothing
            even when every device is healthy and logging. Check the raw
            conn_status values in an unfiltered call before relying on this.
        filters: Structured conditions, each {field, op, value}. They and the
            narrow parameters above are joined into one "&&" chain, since
            dvmdb reads a bare list of conditions as OR. Fields: name, ip, sn,
            hostname, desc, os_ver, mr, patch, platform_str, conn_status,
            dev_status, mgmt_mode, adm_usr, vdom, hdisk_size, build.
            Ops: eq, ne, gt, gte, lt, lte, contains, in, not_in. "in" is an
            OR over its values, nested as one group inside the chain. Not
            supported here (hard error): "not_contains" (no spelling works
            against this endpoint; use "ne" with exact values or exclude
            matches yourself), and "contains" on os_ver, mr and patch, which
            are integers (use "eq" with a number, or os_version_filter).
            Aliases accepted for field names: device_name (name),
            serial/serial_number (sn), os_version (os_ver),
            platform (platform_str), connection_status (conn_status),
            description (desc).
            Example: [{"field": "platform", "op": "contains", "value": "VM"},
                      {"field": "os_ver", "op": "eq", "value": 7}]
        fields: Which keys each device carries. Unlike the log tools this is
            native -- the list is sent to dvmdb, so the untrimmed object never
            crosses the wire. Omit for a curated default (name, ip, sn,
            hostname, os_ver, mr, patch, platform_str, conn_status, dev_status,
            vdom); pass ["*"] for every field the appliance defines, roughly 60
            per device and mostly empty placeholders; or name the fields you
            want. English aliases work here exactly as they do in `filters` --
            serial_number resolves to sn, os_version to os_ver, platform to
            platform_str, connection_status to conn_status.
            Unlike `filters`, a name outside the list above is NOT an error
            here: it is forwarded to dvmdb with a warning, so appliance fields
            this server does not enumerate (``oid``, ``ha_mode``, ``os_type``,
            ``last_checked``, ...) are reachable. A field the appliance does
            not define simply does not appear in the rows.
            The appliance always adds ``oid`` to each object regardless.

    Returns:
        dict: Search results with keys:
            - status: "success" or "error"
            - count: Number of matching devices
            - devices: List of matching device objects. The appliance always
              includes ``oid`` in each object, even under a ``fields``
              projection that does not request it.
            - filter_applied: The compiled filter sent to the appliance, its
              entries joined with "&&", or None when nothing narrowed the
              search
            - fields_returned: The resolved field names sent to dvmdb, or []
              when ``fields=["*"]`` was passed -- the appliance chose the
              shape then, so there is nothing this function can honestly
              claim about it
            - warnings: Field-resolution warnings, if any
            - message: Error message if failed

    Example:
        >>> # Find all FortiGate VMs
        >>> result = await search_devices(platform_filter="FortiGate-VM")

        >>> # Find offline devices
        >>> result = await search_devices(connection_status="down")

        >>> # Find FortiGate VMs on 7.6.x
        >>> result = await search_devices(platform_filter="FortiGate-VM", os_version_filter="7.6")
    """
    try:
        adom = validate_adom(adom or get_default_adom())
        client = _get_client()

        # Every narrow parameter becomes a condition and compiles together with
        # ``filters`` in one call. compile_to_array is the only place entries
        # are joined, and dvmdb reads a bare list of entries as an OR (#146):
        # anything appended outside it would widen the search instead of
        # narrowing it. ``contains`` compiles to ``like`` there as well.
        conditions: list[FilterCondition] = []
        if name_filter:
            conditions.append(FilterCondition(field="name", op="contains", value=name_filter))
        if platform_filter:
            conditions.append(
                FilterCondition(field="platform_str", op="contains", value=platform_filter)
            )
        if os_version_filter:
            conditions.extend(_os_version_conditions(os_version_filter))
        if connection_status:
            # Coercion lives in the query vocabulary now, so "down" means 2
            # here and everywhere else that filters on conn_status. The
            # rejection is re-phrased in terms of this parameter's own name:
            # a caller who passed connection_status= should not be told about
            # a field called conn_status they never mentioned.
            try:
                status_val = coerce_value("device", "conn_status", connection_status)
            except ValidationError:
                valid = ", ".join(sorted(get_vocabulary("device").coercions["conn_status"]))
                return error_response(
                    error="validation_error",
                    message=(
                        f"Invalid connection_status '{connection_status}'. Must be one of: {valid}"
                    ),
                    operation="search_devices",
                    adom=adom,
                )
            conditions.append(FilterCondition(field="conn_status", op="eq", value=status_val))
        if filters:
            conditions.extend(filters)
        entries, _ = compile_to_array(conditions, "device")

        projection, projection_warnings = resolve_projection("device", fields)
        # dvmdb projects natively, so send the names rather than trimming the
        # response: a subset chosen here would still have crossed the wire whole.
        # sorted() so the wire payload is deterministic and diffable in a trace.
        field_list = sorted(projection) if projection is not None else None

        devices = await client.list_devices(
            adom=adom,
            filter=entries if entries else None,
            fields=field_list,
        )

        return {
            "status": "success",
            "count": len(devices),
            # DVMDB device objects carry credential material (adm_pass, etc.);
            # mask it before returning over MCP.
            "devices": sanitize_for_logging(devices),
            # Echo what was actually sent so a caller can verify the compiled
            # filter instead of inferring it from which rows came back.
            "filter_applied": entries if entries else None,
            "fields_returned": field_list if field_list is not None else [],
            "warnings": projection_warnings,
        }
    except ValidationError as e:
        return error_response(
            error="validation_error", message=e, operation="search_devices", adom=adom
        )
    except Exception as e:
        logger.error(f"Failed to search devices: {e}")
        return error_response(
            error="faz_operation_failed", message=e, operation="search_devices", adom=adom
        )
