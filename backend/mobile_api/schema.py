from drf_spectacular.generators import EndpointEnumerator, SchemaGenerator


class MobileEndpointEnumerator(EndpointEnumerator):
    def should_include_endpoint(self, path, callback):
        return path.startswith('/api/v1/mobile/') and super().should_include_endpoint(path, callback)


class MobileSchemaGenerator(SchemaGenerator):
    endpoint_inspector_cls = MobileEndpointEnumerator