"""Service-type plugin registry. Generic — imports no service SDK.

A `drivers/` module describes one service type by constructing a `Driver`.
The entrypoint collects the drivers and builds a `Registry`, which it injects
into the common code. Common code asks the registry for service-type
behaviour; it never imports a driver or an SDK itself.
"""


class Driver:
    """Capabilities of one service type, supplied by a `drivers/` module.

    names         -- driver-name strings this plugin handles, e.g. ["s3"]
    storage_kind  -- "file", "db", or "other" (orients input vs. output)
    inspect       -- callable(attrs: dict) -> inventory dict
    excluded_asset-- optional callable(asset_name, locator) -> reason | None
                     for per-source-type asset exclusion rules
    """

    def __init__(self, names, storage_kind, inspect, excluded_asset=None):
        self.names = list(names)
        self.storage_kind = storage_kind
        self.inspect = inspect
        self.excluded_asset = excluded_asset or (lambda *_: None)


class Registry:
    """Looks up service-type behaviour by driver name."""

    def __init__(self, drivers):
        self._by_name = {}
        for d in drivers:
            for name in d.names:
                self._by_name[name] = d

    def supports(self, driver_name):
        return driver_name in self._by_name

    def inspector(self, driver_name):
        """The inspect callable for a driver, or None if unsupported."""
        d = self._by_name.get(driver_name)
        return d.inspect if d else None

    def storage_kind(self, driver_name):
        d = self._by_name.get(driver_name)
        return d.storage_kind if d else "other"

    def excluded_asset(self, driver_name, asset_name, locator):
        """Per-source-type asset exclusion reason, or None."""
        d = self._by_name.get(driver_name)
        return d.excluded_asset(asset_name, locator) if d else None
