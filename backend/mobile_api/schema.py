from drf_spectacular.generators import EndpointEnumerator, SchemaGenerator


class MobileEndpointEnumerator(EndpointEnumerator):
    def should_include_endpoint(self, path, callback):
        return path.startswith('/api/v1/mobile/') and super().should_include_endpoint(path, callback)


class MobileSchemaGenerator(SchemaGenerator):
    endpoint_inspector_cls = MobileEndpointEnumerator


def mobile_error_contract(result, generator, request, public):
    if not isinstance(generator, MobileSchemaGenerator):
        return result
    from .views import MobileAuthenticatedView
    for path, _, method, callback in generator.endpoints:
        if issubclass(callback.cls, MobileAuthenticatedView):
            operation = result.get("paths", {}).get(path, {}).get(method.lower())
            if operation is not None:
                operation["security"] = [{"MobileBearer": []}]
                operation.setdefault("responses", {}).setdefault("401", {"description": "Invalid or revoked bearer session"})
    result.setdefault("components", {}).setdefault("schemas", {})["MobileErrorResponse"] = {
        "type": "object", "required": ["error"], "properties": {
            "error": {"type": "object", "required": ["code", "message", "details"], "properties": {
                "code": {"type": "string"}, "message": {"type": "string"},
                "retry_after": {"type": "integer", "minimum": 0},
                "details": {"type": "array", "items": {"type": "object", "required": ["field", "message"],
                                                     "properties": {"field": {"type": "string"}, "message": {"type": "string"}}}},
            }},
        },
    }
    for path in result.get("paths", {}).values():
        for method, operation in path.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            responses = operation.setdefault("responses", {})
            responses.setdefault("default", {
                "description": "Controlled failures use the error envelope; unhandled server/proxy failures may be non-JSON.",
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/MobileErrorResponse"}},
                    "text/html": {"schema": {"type": "string"}},
                    "text/plain": {"schema": {"type": "string"}},
                },
            })
            for code, response in responses.items():
                if code.isdigit() and 400 <= int(code) < 600:
                    response["content"] = {"application/json": {"schema": {"$ref": "#/components/schemas/MobileErrorResponse"}}}
    return result