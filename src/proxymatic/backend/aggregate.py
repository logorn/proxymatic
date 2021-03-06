import logging
import threading

class AggregateBackend(object):
    def __init__(self, exposehost):
        self._exposehost = exposehost
        self._backends = []
        self._sources = {}
        self._lock = threading.RLock()
        self._prev = {}

    def add(self, backend):
        self._backends.append(backend)

    def update(self, source, services):
        """
        @param source Discovery source that originated this update, e.g. Marathon or etcd
        @param services Services found by the discovery source
        """
        with self._lock:
            # Merged updated services into existing ones to keep server backends being reordered
            prev = self._sources.get(source, {})
            next = {}
            for key, service in services.items():
                if key in prev:
                    next[key] = prev[key].update(service)
                else:
                    next[key] = service
            self._sources[source] = next

            # Merge services from multiple sources in source priority order (Marathon has precedence)
            merged = {}
            for source, chunk in sorted(self._sources.items(), cmp=lambda a, b: cmp(a[0].priority, b[0].priority)):
                for key, service in chunk.items():
                    if self._accepts(service):
                        merged[key] = service

            # Log changes to services and server backends
            for key, service in merged.items():
                if key not in self._prev:
                    logging.info("Added %s", service)
                elif self._prev[key] != service:
                    logging.info("Modified %s to %s", self._prev[key], service)
            for key, service in self._prev.items():
                if key not in merged:
                    logging.info("Removed %s", service)

            # Apply config changes
            remaining = dict(merged)
            for backend in self._backends:
                accepted = backend.update(self, remaining)
                for key in accepted.keys():
                    del remaining[key]

            # Remember the state until next update
            self._prev = merged

    def _accepts(self, service):
        # Filter services running in net=host mode
        for server in service.servers:
            if not self._exposehost and server.port == str(service.port):
                return False

        return True
